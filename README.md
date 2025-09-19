# LDAP_MAILCOW - Alias Synchronization

Синхронизирует алиасы пользователей и групп из LDAP (например, Active Directory) с mailcow-dockerized. Этот инструмент предназначен для работы только с алиасами и не создает почтовые ящики пользователей.

* [Как это работает](#как-это-работает)
* [Использование](#использование)
  * [Алиасы пользователей](#алиасы-пользователей)
  * [Алиасы групп](#алиасы-групп)
  * [Отключение удаленных пользователей](#отключение-удаленных-пользователей)
* [Ограничения](#ограничения)
* [Кастомизация и поддержка интеграции](#кастомизация-и-поддержка-интеграции)

## Как это работает

Python-скрипт периодически проверяет LDAP и создает/обновляет алиасы в mailcow через API:

1. **Алиасы пользователей**: извлекает алиасы из атрибута `proxyAddresses` пользователей LDAP
2. **Алиасы групп**: создает алиасы для групп LDAP, где адрес группы направляет на всех участников группы
3. **Опционально**: отключает пользователей, которые больше не найдены в LDAP (если включено)

## Использование

1. Создайте директорию `data/db`. В ней будет храниться SQLite база данных для синхронизации.
2. Создайте (или обновите) ваш `docker-compose.override.yml` с дополнительным контейнером:

    ```yaml
    version: '2.1'
    services:

        ldap-mailcow:
            image: 'ghcr.io/lazygatto/custommailcow-ldap:latest'
            network_mode: host
            container_name: mailcowcustomized_ldap-mailcow
            depends_on:
                - nginx-mailcow
            volumes:
                - ./data/ldap:/db:rw
            restart: unless-stopped
            environment:
                - LDAP_MAILCOW_LDAP_URI=ldap(s)://dc.example.local
                - LDAP_MAILCOW_LDAP_BASE_DN=OU=Mail Users,DC=example,DC=local
                - LDAP_MAILCOW_LDAP_BIND_DN=CN=Bind DN,CN=Users,DC=example,DC=local
                - LDAP_MAILCOW_LDAP_BIND_DN_PASSWORD=BindPassword
                - LDAP_MAILCOW_API_HOST=https://mailcow.example.local
                - LDAP_MAILCOW_API_KEY=XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX
                - LDAP_MAILCOW_SYNC_INTERVAL=300
                - LDAP_MAILCOW_LDAP_FILTER=(&(objectClass=user)(objectCategory=person)(memberOf:1.2.840.113556.1.4.1941:=CN=Group,CN=Users,DC=example DC=local))
                - LDAP_MAILCOW_LDAP_GROUP_FILTER=(&(objectClass=group)(mail=*))
                - LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER=(&(objectClass=person)(mail=*)(distinguishedName={MEMBER_CN}))
                - LDAP_MAILCOW_DISABLE_DELETED_USERS=false
    ```

3. Настройте переменные окружения:

    **Обязательные переменные:**
    * `LDAP_MAILCOW_LDAP_URI` - URI LDAP сервера (например, Active Directory). Должен быть доступен из контейнера. Формат: `protocol://host:port`, например `ldap://localhost` или `ldaps://secure.domain.org`
    * `LDAP_MAILCOW_LDAP_BASE_DN` - базовый DN где находятся учетные записи пользователей
    * `LDAP_MAILCOW_LDAP_BIND_DN` - DN специальной учетной записи LDAP для поиска пользователей
    * `LDAP_MAILCOW_LDAP_BIND_DN_PASSWORD` - пароль для bind DN учетной записи
    * `LDAP_MAILCOW_API_HOST` - URL API mailcow. Убедитесь, что он включен и доступен из контейнера для чтения и записи
    * `LDAP_MAILCOW_API_KEY` - ключ API mailcow (чтение/запись)
    * `LDAP_MAILCOW_SYNC_INTERVAL` - интервал в секундах между синхронизациями LDAP

    **Опциональные LDAP фильтры:**
    * `LDAP_MAILCOW_LDAP_FILTER` - LDAP фильтр для поиска пользователей, по умолчанию `(&(objectClass=user)(objectCategory=person))`
    * `LDAP_MAILCOW_LDAP_GROUP_FILTER` - LDAP фильтр для поиска групп и создания алиасов, по умолчанию `(&(objectClass=group)(mail=*))`
    * `LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER` - LDAP фильтр для поиска участников группы, по умолчанию `(&(objectClass=person)(mail=*)(distinguishedName={MEMBER_CN}))`. Сохраните `{MEMBER_CN}`, так как он заменяется во время выполнения скрипта.

    **Опциональные переменные управления:**
    * `LDAP_MAILCOW_DISABLE_DELETED_USERS` - включить отключение пользователей, удаленных из LDAP (по умолчанию `false`). Установите в `true`, если хотите, чтобы скрипт отключал пользователей, которые больше не найдены в LDAP.

4. Запустите дополнительный контейнер: `docker compose up -d ldap-mailcow`
5. Проверьте логи `docker compose logs ldap-mailcow` (или `docker compose logs --tail=100 ldap-mailcow` для сокращения вывода)

### Алиасы пользователей

Скрипт поддерживает алиасы пользователей, которые должны быть установлены в Active Directory в атрибуте `proxyAddresses`.
Формат записей: `smtp:username@domain.com`
Вы можете добавить столько алиасов, сколько нужно для каждого пользователя.

### Алиасы групп

Скрипт автоматически создает алиасы для групп LDAP:
- Адрес алиаса берется из атрибута `mail` группы
- Алиас направляет письма на всех участников группы, у которых есть атрибут `mail`
- При изменении состава группы алиас автоматически обновляется

### Отключение удаленных пользователей

Если установлена переменная `LDAP_MAILCOW_DISABLE_DELETED_USERS=true`, скрипт будет отключать пользователей в mailcow, которые больше не найдены в LDAP. Это полезно, если вы не используете встроенную синхронизацию пользователей mailcow.

Если переменная не установлена или установлена в `false`, эта функция отключена, что подходит для использования со встроенной синхронизацией пользователей mailcow.

## Ограничения

### Только алиасы

Этот инструмент предназначен только для синхронизации алиасов. Он НЕ создает почтовые ящики пользователей. Используйте встроенную функциональность mailcow для синхронизации пользователей или создавайте их вручную.

### Односторонняя синхронизация

Алиасы из вашего LDAP каталога будут добавлены (и деактивированы при удалении/отключении) в вашу базу данных mailcow. Обратная синхронизация не выполняется, и это сделано намеренно.

### Совместимость

Эта версия была написана и протестирована только с Active Directory на контроллере домена Windows Server 2019.
Работа с OpenLDAP или другими реализациями LDAP не тестировалась.

## Кастомизация и поддержка интеграции

Оригинальный инструмент был создан [Programmierus](https://github.com/Programmierus/LDAP_MAILCOW).
Эта версия является форком от форка [rinkp](https://github.com/rinkp/custommailcow-ldap)

Если вы запускаете ваш сервер mailcow за Nginx Proxy Manager - вы можете проверить [этот репозиторий](https://github.com/LazyGatto/npm-cert-export) с дополнительным скриптом для экспорта SSL сертификата в mailcow.

**Вы всегда можете [связаться со мной](mailto:lazygatto@gmail.com) для помощи с интеграцией или для кастомных модификаций на платной основе. Моя текущая почасовая ставка (отслеживается ActivityWatch) составляет 50$ с минимальным обязательством 3 часа.**