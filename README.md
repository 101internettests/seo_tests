# SEO Парсер с интеграцией Google Sheets

Этот проект представляет собой автоматизированный SEO парсер, который анализирует количество заголовков на веб-страницах и загружает результаты в Google таблицы.

## Возможности

- ✅ Подсчет заголовков H1-H6 на веб-страницах
- ✅ Исключение пустых заголовков из подсчета
- ✅ Сравнение с предыдущими результатами
- ✅ Автоматическая загрузка результатов в Google Sheets
- ✅ Сохранение результатов в локальные файлы
- ✅ Подробное логирование
- ✅ Конфигурируемые настройки

## Установка

1. **Клонируйте репозиторий:**
```bash
git clone <repository-url>
cd seo_tests
```

2. **Создайте виртуальное окружение:**
```bash
python -m venv .venv
```

3. **Активируйте виртуальное окружение:**
```bash
# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

4. **Установите зависимости:**
```bash
pip install -r requirements.txt
```

## Настройка Google Sheets API

### 1. Создание проекта в Google Cloud Console

1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект или выберите существующий
3. Включите Google Sheets API:
   - Перейдите в "APIs & Services" > "Library"
   - Найдите "Google Sheets API"
   - Нажмите "Enable"

### 2. Создание учетных данных

1. Перейдите в "APIs & Services" > "Credentials"
2. Нажмите "Create Credentials" > "OAuth 2.0 Client IDs"
3. Выберите тип приложения "Desktop application"
4. Скачайте JSON файл с учетными данными
5. Переименуйте файл в `credentials.json` и поместите в корень проекта

### 3. Настройка прав доступа к таблице

1. Откройте вашу Google таблицу
2. Нажмите "Share" (Поделиться)
3. Добавьте email из учетных данных Google API
4. Предоставьте права "Editor"

## Конфигурация

### Создание файла конфигурации

```bash
python main.py --create-config
```

Это создаст файл `config.json` с настройками по умолчанию:

```json
{
  "urls": [
    "https://piter-online.net/",
    "https://piter-online.net/domashniy-internet/podklyuchit-deshevyj-internet",
    "https://piter-online.net/domashniy-internet/podklyuchit-wifi"
  ],
  "spreadsheet_id": "1NTyI48H4woktkCqnvjGsMOWZbnqs8oCMMNP3j_AJDkw",
  "sheet_name": "Лист1",
  "upload_to_sheets": true,
  "save_local": true,
  "delay_between_requests": 2
}
```

### Параметры конфигурации

- `urls`: Список URL для анализа
- `spreadsheet_id`: ID Google таблицы (из URL)
- `sheet_name`: Название листа в таблице
- `upload_to_sheets`: Загружать ли результаты в Google Sheets
- `save_local`: Сохранять ли результаты локально
- `delay_between_requests`: Задержка между запросами (секунды)

## Использование

### Базовый запуск

```bash
python main.py
```

### Запуск с пользовательскими URL

```bash
python main.py --urls https://example.com https://example.com/page1
```

### Запуск без загрузки в Google Sheets

```bash
python main.py --no-sheets
```

### Запуск без локального сохранения

```bash
python main.py --no-local
```

### Использование пользовательского файла конфигурации

```bash
python main.py --config my_config.json
```

## Структура результатов

### В Google Sheets

Результаты загружаются в таблицу со следующими столбцами:

| Столбец | Описание |
|---------|----------|
| Дата и время | Время выполнения анализа |
| URL | Анализируемый URL |
| Статус | Статус анализа (success/error) |
| H1-H6 (непустые) | Количество непустых заголовков |
| H1-H6 (всего) | Общее количество заголовков |
| Сравнение статус | Статус сравнения с предыдущими данными |
| Ошибки | Список ошибок при сравнении |
| Изменения | Список изменений |

### Локальные файлы

Результаты сохраняются в JSON формате:

```json
{
  "url": "https://example.com",
  "timestamp": "2024-01-01T12:00:00",
  "status": "success",
  "headings": {
    "h1_total": 1,
    "h1_non_empty": 1,
    "h2_total": 5,
    "h2_non_empty": 5
  },
  "comparison": {
    "status": "success",
    "changes": {},
    "errors": []
  }
}
```

## Логирование

Все действия записываются в файл `seo_parser.log` и выводятся в консоль.

## Алгоритм работы

1. **Загрузка предыдущих данных** - загружаются результаты предыдущего анализа
2. **Анализ страниц** - для каждого URL:
   - Получение HTML содержимого
   - Подсчет заголовков H1-H6
   - Исключение пустых заголовков
3. **Сравнение** - сравнение с предыдущими результатами:
   - Ошибка: если количество заголовков уменьшилось
   - Успех: если количество осталось прежним или увеличилось
4. **Сохранение** - сохранение новых данных как базовых для следующего сравнения
5. **Экспорт** - загрузка результатов в Google Sheets и локальные файлы

## Примеры использования

### Ежедневный мониторинг

Создайте cron job или планировщик задач:

```bash
# Linux/Mac (crontab)
0 9 * * * cd /path/to/seo_tests && python main.py

# Windows (Task Scheduler)
# Создайте задачу для запуска main.py каждый день в 9:00
```

### Анализ новых страниц

```bash
python main.py --urls https://new-site.com https://new-site.com/about
```

### Тестирование без загрузки в таблицу

```bash
python main.py --no-sheets --urls https://test-site.com
```

## Устранение неполадок

### Ошибка аутентификации Google API

1. Убедитесь, что файл `credentials.json` находится в корне проекта
2. Удалите файл `token.pickle` и перезапустите скрипт
3. Проверьте, что Google Sheets API включен в проекте

### Ошибка доступа к таблице

1. Убедитесь, что email из учетных данных имеет права "Editor" на таблицу
2. Проверьте правильность `spreadsheet_id` в конфигурации

### Ошибки сети

1. Проверьте интернет-соединение
2. Увеличьте `delay_between_requests` в конфигурации
3. Проверьте доступность анализируемых сайтов

## Структура проекта

```
seo_tests/
├── main.py              # Основной скрипт
├── seo_parser.py        # Парсер SEO данных
├── google_sheets.py     # Работа с Google Sheets API
├── config.json          # Конфигурация (создается автоматически)
├── requirements.txt     # Зависимости
├── README.md           # Документация
├── credentials.json    # Учетные данные Google API (нужно добавить)
├── token.pickle        # Токен авторизации (создается автоматически)
├── headings_data.json  # Данные о заголовках (создается автоматически)
└── seo_parser.log      # Лог файл (создается автоматически)
```

## Лицензия

MIT License