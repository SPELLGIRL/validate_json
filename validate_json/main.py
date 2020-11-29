import json
from datetime import datetime
from pathlib import Path
from jsonschema import Draft7Validator
from typing import Union
import logging

PATH_TO_SHEMA = Path('./schema')
PATH_TO_EVENT = Path('./event')


class UnknownError:
    """Класс неизвестной ошибки."""
    message = 'Неизвестная ошибка'

    def __str__(self):
        return self.message


class CorruptedSchema:
    """Класс поврежденной схемы."""

    def __init__(self, error=None):
        self.error = error or UnknownError()

    def __str__(self):
        return f"Схема некорректна: {self.error}"


def remove_empty_from_dict(d: Union[dict, list, None]) -> Union[dict, list]:
    """Функция удаляет пустые значения в массиве."""
    if type(d) is dict:
        _temp = {}
        for k, v in d.items():
            if v is None or v == "":
                pass
            elif type(v) is int or type(v) is float:
                _temp[k] = remove_empty_from_dict(v)
            elif v or remove_empty_from_dict(v):
                _temp[k] = remove_empty_from_dict(v)
        return _temp
    elif type(d) is list:
        return [
            remove_empty_from_dict(v)
            for v in d if (
                    (str(v).strip() or str(remove_empty_from_dict(v)).strip())
                    and (v is not None or remove_empty_from_dict(
                v) is not None)
            )
        ]
    else:
        return d


def validate_path() -> bool:
    """Функция проверяет пути"""
    is_schema_path = PATH_TO_SHEMA.exists() and PATH_TO_SHEMA.is_dir()
    is_event_path = PATH_TO_EVENT.exists() and PATH_TO_EVENT.is_dir()
    return is_event_path and is_schema_path


def schema_loader() -> dict:
    """
    Функция загрузки схемы
    :return: Возвращает словарь со схемами.
    """
    schemas = {}
    for schema_path in PATH_TO_SHEMA.iterdir():
        filename = schema_path.stem
        try:
            with open(schema_path, 'r', encoding='utf8') as schema:
                json_schema = json.load(schema)
                Draft7Validator.check_schema(json_schema)
                schemas[filename] = Draft7Validator(json_schema)
        except Exception as err:
            schemas[filename] = CorruptedSchema(err)
    return schemas


def reader(path: str) -> dict:
    """
    Функция читает файлы по заданному пути.
    :param path: Путь к файлу.
    :return: Возвращает словарь с данными из файла.
    """
    with open(path, 'r', encoding='utf-8') as file:
        result = json.load(file)
    return result


def check_event_key(event: str) -> list:
    """
    Функция проверяет ключ event в JSON файлах.
    :param event: Строка с названием схемы в JSON файле.
    :return: Возвращает список ошибок при проверке значения event.
    """
    errors = []
    if event is None:
        errors.append('Не задана схема для проверки.')
    elif not isinstance(event, str):
        errors.append('В качестве названия схемы должна быть строка')
    return errors


def check_schema_key(name: str, schemas: dict) -> list:
    """
    Функция проверки названия схемы.
    :param name: Строка с названием схемы.
    :param schemas: Словарь схем.
    :return: Возвращает список ошибок схемы.
    """
    errors = []
    if schemas.get(name) is None:
        errors.append('Указанной схемы не существует.')
    elif schemas[name] is CorruptedSchema:
        errors.append('В указанной схеме выявлены ошибки')
    return errors


def check_data_key(data):
    """
    Функция проверки ключа data JSON файла.
    :return: Возвращает список ошибок.
    """
    errors = []
    if data is None:
        errors.append('Не указаны данные для проверки.')
    return errors


def run_checker(schemas: dict) -> dict:
    """
    Функция проверки соответствия JSON файла указанной схеме.
    :param schemas: Словарь со схемами.
    :return: result Возвращает словарь ошибок.
    """
    files_paths = list(PATH_TO_EVENT.iterdir())
    errors = {path.stem: [] for path in files_paths}
    for event_path in files_paths:
        file_error_list = errors[event_path.stem]
        try:
            event_json = reader(f"{event_path}")
        except Exception:
            file_error_list.append('Данный файл не соответствует формату JSON')
            continue
        if not isinstance(event_json, dict):
            file_error_list.append(
                'Файл должен содержать словарь с данными в формате JSON')
            continue

        event_errors = check_event_key(event_json.get("event"))
        file_error_list.extend(event_errors)

        data_errors = check_data_key(event_json.get("data"))
        file_error_list.extend(data_errors)

        if not event_errors:
            schema_name_errors = check_schema_key(event_json["event"], schemas)
            file_error_list.extend(schema_name_errors)

            if not (schema_name_errors or data_errors):
                file_error_list.extend(
                    check_data(
                        event_json['data'],
                        schemas[event_json["event"]]
                    )
                )
    result = {
        "schema_errors": {
            k: f'{v}' for k, v in schemas.items() if
            isinstance(v, CorruptedSchema)
        },
        "json_errors": errors
    }

    logger.info(result)
    return result


def check_data(data: dict, validator: Draft7Validator) -> list:
    """
    Проверка значения data на соответствие схеме.
    :param data: Словарь данных из JSON файла.
    :param validator: Объект Draft7Validator.
    :return: result Возвращает список найденных ошибок.
    """
    result = [
        error.message
        for error in sorted(validator.iter_errors(data), key=str)
    ]
    if result:
        logger.info(result)
    return result


def make_report(result: dict) -> list:
    """
    Функция генерирует отчет об ошибках.
    :param result: Результрующий словарь для создания отчёта.
    :return: Список, содержащий информацию по ошибкам.
    """
    res = [f"Проведена проверка {datetime.now()}\n", "\n"]
    if "schema_errors" in result:
        res.append(f"Выявлены ошибки схемы:\n")
        for name, error in result["schema_errors"].items():
            res.append(f"\tВ схеме {name} обнаружены ошибки:\n")
            res.append(f"\t{error}\n")
    if "json_errors" in result:
        res.append(f"Выявлены ошибки JSON файла:\n")
        for name, errors in result["json_errors"].items():
            res.append(f"\tВ файле {name} обнаружены ошибки:\n")
            for error in errors:
                res.append(f"\t{error}\n")
    logger.info(res)
    return res


def write_report(result: list):
    """
    Функция записывает результат в текстовый файл.
    :param result: Список, содержащий отчет.
    :return: Возвращает файл с записанным результатом.
    """
    with open('report.txt', 'w+', encoding='utf-8') as file:
        file.writelines(result)


def main():
    """Функция запуска."""
    logger.info('Запущен скрипт проверки!')
    # Проверка путей.
    validate_path()
    # Загрузка файлов схем.
    schemas = schema_loader()
    # Запуск функции проверки соответствия.
    result = run_checker(schemas)
    # Удаление пустых строк из результирующего словаря.
    res = remove_empty_from_dict(result)
    # Создание отчёта.
    report = make_report(res)
    # Запись отчёта в файл.
    write_report(report)


if __name__ == '__main__':
    # Создание объекта логирования.
    logger = logging.getLogger('json_validator')
    f_handler = logging.FileHandler('logfile.log')
    # Настройка логера.
    logger.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.INFO)
    f_handler.setLevel(logging.DEBUG)
    f_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    f_handler.setFormatter(f_format)
    c_handler.setFormatter(f_format)
    logger.addHandler(f_handler)
    logger.addHandler(c_handler)
    # Вызов запуска скрипта.
    main()
