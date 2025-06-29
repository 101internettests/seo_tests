# Быстрое решение проблемы OAuth 403

## Проблема
```
Приложение "101" ещё не прошло проверку Google. До завершения процесса приложение доступно только тестировщикам, одобренным разработчиком.
Ошибка 403: access_denied
```

## Решение 1: Добавить себя как тестировщика (5 минут)

1. **Откройте Google Cloud Console:**
   - https://console.cloud.google.com/
   - Выберите ваш проект

2. **Перейдите в OAuth согласие:**
   - "APIs & Services" > "OAuth consent screen"

3. **Добавьте тестировщика:**
   - В разделе "Test users" нажмите "Add Users"
   - Введите ваш Google email
   - Нажмите "Save"

4. **Перезапустите скрипт:**
   ```bash
   python main.py
   ```

## Решение 2: Использовать Service Account (рекомендуется)

Service Account не требует проверки Google и работает сразу.

### Шаг 1: Создать Service Account

1. **В Google Cloud Console:**
   - "APIs & Services" > "Credentials"
   - "Create Credentials" > "Service Account"

2. **Заполните форму:**
   - Name: `seo-parser`
   - Description: `Service account for SEO parser`
   - Нажмите "Create and Continue"
   - Нажмите "Continue" (роли не нужны)
   - Нажмите "Done"

3. **Создайте ключ:**
   - Нажмите на созданный Service Account
   - Вкладка "Keys" > "Add Key" > "Create new key"
   - Выберите "JSON" > "Create"
   - Скачайте файл и переименуйте в `service-account-key.json`
   - Поместите в корень проекта

### Шаг 2: Настройте права доступа

1. **Откройте файл `service-account-key.json`**
2. **Найдите поле `client_email`** (например: `seo-parser@project-id.iam.gserviceaccount.com`)
3. **Добавьте этот email в права доступа к таблице:**
   - Откройте вашу Google таблицу
   - Нажмите "Share" (Поделиться)
   - Введите email из `client_email`
   - Выберите права "Editor"
   - Нажмите "Share"

### Шаг 3: Запустите с Service Account

```bash
python main_service_account.py
```

## Решение 3: Отправить на проверку Google

Если хотите использовать OAuth для всех пользователей:

1. **В OAuth consent screen:**
   - "Publishing status" > "Submit for verification"
   - Заполните форму:
     - App name: `SEO Parser`
     - User support email: ваш email
     - App description: `SEO parser for analyzing website headings`
     - Developer contact: ваш email
   - Нажмите "Submit for verification"

2. **Ждите проверки Google** (может занять несколько дней)

## Рекомендация

**Используйте Решение 2 (Service Account)** - это самый быстрый и надежный способ, который не требует проверки Google.

## Проверка работы

После настройки запустите тест:

```bash
# Тест без Google Sheets
python test_parser.py

# Тест с Service Account
python main_service_account.py --no-sheets
```