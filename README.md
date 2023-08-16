# LDAP_MAILCOW

Adds LDAP accounts, user aliases and group aliases to mailcow-dockerized and enables LDAP (e.g., Active Directory) authentication.

* [How does it work](#how-does-it-work)
* [Usage](#usage)
  * [User Aliases](#user-aliases)
  * [LDAP Fine-tuning](#ldap-fine-tuning)
* [Limitations](#limitations)
  * [Startup problem](#startup-problem)
  * [WebUI and EAS authentication](#webui-and-eas-authentication)
  * [Two-way sync](#two-way-sync)
* [Customizations and Integration support](#customizations-and-integration-support)

## How does it work

A python script periodically checks and creates new LDAP accounts and deactivates deleted and disabled ones with mailcow API. It also enables LDAP authentication in SOGo and dovecot.

## Usage

1. Create a `data/db` directory. SQLite database for synchronization will be stored there.
2. Create (or update) your `docker-compose.override.yml` with an additional container:

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
                - ./data/conf/dovecot:/conf/dovecot:rw
                - ./data/conf/sogo:/conf/sogo:rw
            restart: unless-stopped
            environment:
                - LDAP_MAILCOW_LDAP_URI=ldap(s)://dc.example.local
                - LDAP_MAILCOW_LDAP_GC_URI=ldap://dc.example.local:3268
                - LDAP_MAILCOW_LDAP_DOMAIN=domain.com
                - LDAP_MAILCOW_LDAP_BASE_DN=OU=Mail Users,DC=example,DC=local
                - LDAP_MAILCOW_LDAP_BIND_DN=CN=Bind DN,CN=Users,DC=example,DC=local
                - LDAP_MAILCOW_LDAP_BIND_DN_PASSWORD=BindPassword
                - LDAP_MAILCOW_API_HOST=https://mailcow.example.local
                - LDAP_MAILCOW_API_KEY=XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX
                - LDAP_MAILCOW_API_QUOTA=3072
                - LDAP_MAILCOW_SYNC_INTERVAL=300
                - LDAP_MAILCOW_LDAP_FILTER=(&(objectClass=user)(objectCategory=person)(memberOf:1.2.840.113556.1.4.1941:=CN=Group,CN=Users,DC=example DC=local))
                - LDAP_MAILCOW_SOGO_LDAP_FILTER=objectClass='user' AND objectCategory='person' AND memberOf:1.2.840.113556.1.4.1941:='CN=Group,CN=Users,DC=example DC=local'
                - LDAP_MAILCOW_LDAP_GROUP_FILTER=(&(objectClass=group)(mail=*))
                - LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER=(&(objectClass=person)(mail=*)(distinguishedName={MEMBER_CN}))
    ```

3. Configure environmental variables:

    * `LDAP_MAILCOW_LDAP_URI` - LDAP (e.g., Active Directory) URI (must be reachable from within the container). The URIs are in syntax `protocol://host:port`. For example `ldap://localhost` or `ldaps://secure.domain.org`
    * `LDAP_MAILCOW_LDAP_GC_URI` - LDAP (e.g., Active Directory) Global Catalog URI (must be reachable from within the container). The URIs are in syntax `protocol://host:port`. For example `ldap://localhost:3268` or `ldaps://secure.domain.org:3269`
    * `LDAP_MAILCOW_LDAP_DOMAIN` - domain for you mail account, ie `domain.com`
    * `LDAP_MAILCOW_LDAP_BASE_DN` - base DN where user accounts can be found
    * `LDAP_MAILCOW_LDAP_BIND_DN` - bind DN of a special LDAP account that will be used to browse for users
    * `LDAP_MAILCOW_LDAP_BIND_DN_PASSWORD` - password for bind DN account
    * `LDAP_MAILCOW_API_HOST` - mailcow API url. Make sure it's enabled and accessible from within the container for both reads and writes
    * `LDAP_MAILCOW_API_KEY` - mailcow API key (read/write)
    * `LDAP_MAILCOW_API_QUOTA` - mailcow qouta for new mailboxes, in MB, ie 3072 for 3GB. If set to 0 quota will be disabled.
    * `LDAP_MAILCOW_SYNC_INTERVAL` - interval in seconds between LDAP synchronizations
    * **Optional** LDAP filters (see example above). SOGo uses special syntax, so you either have to **specify both or none**:
        * `LDAP_MAILCOW_LDAP_FILTER` - LDAP filter to apply, defaults to `(&(objectClass=user)(objectCategory=person))`
        * `LDAP_MAILCOW_SOGO_LDAP_FILTER` - LDAP filter to apply for SOGo ([special syntax](https://sogo.nu/files/docs/SOGoInstallationGuide.html#_authentication_using_ldap)), defaults to `objectClass='user' AND objectCategory='person'`
    * **Additional optional** LDAP filters to parse Groups and create aliases with mail of its members
        * `LDAP_MAILCOW_LDAP_GROUP_FILTER` - LDAP filter to apply, for finding group mail and create aliases, defaults to `(&(objectClass=group)(mail=*))`
        * `LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER` - LDAP filter to apply, for finding group member mail for adding into aliases, defaults to `(&(objectClass=person)(mail=*)(distinguishedName={MEMBER_CN}))`, keep `{MEMBER_CN}`, as it will replaced while running the script.

4. Start additional container: `docker compose up -d ldap-mailcow`
5. Check logs `docker compose logs ldap-mailcow` (or `docker compose logs --tail=100 ldap-mailcow` to reduce logs output)
6. Restart dovecot and SOGo if necessary `docker compose restart sogo-mailcow dovecot-mailcow`

### User Aliases

This version of script has support for user aliases too. They needed to be set in Active Directory in `proxyAddresses` attribute.
Format records in such way: `smtp:username@domain.com`
You can add as many aliases as you need for every user.

### LDAP Fine-tuning

Container internally uses the following configuration templates:

* SOGo: `/templates/sogo/plist_ldap`
* dovecot: `/templates/dovecot/ldap/passdb.conf`

This version was written and tested only at Active Directory running on Windows Server 2019 domain controller.
So, I dont know how it will sync with OpenLDAP or any other LDAP implementation.

If necessary, you can edit and remount them through docker volumes. Some documentation on these files can be found here: [dovecot](https://doc.dovecot.org/configuration_manual/authentication/ldap/), [SOGo](https://sogo.nu/files/docs/SOGoInstallationGuide.html#_authentication_using_ldap)

## Limitations

### Startup problem

While restart all containers with `docker compose up` **ldap-mailcow** may stop due to error, because API not ready. It has to be done in `depends` directive, or 
so on. But I dont have idea how to do that for now ;)

### WebUI and EAS authentication

This tool enables authentication for Dovecot and SOGo, which means you will be able to log into POP3, SMTP, IMAP, and SOGo Web-Interface. **You will not be able to log into mailcow UI or EAS using your LDAP credentials by default.**

As a workaround, you can hook IMAP authentication directly to mailcow by adding the following code above [this line](https://github.com/mailcow/mailcow-dockerized/blob/d6c3c58f429a4cd9d4bcf6f2f3ab0dc2c13b00f8/data/web/inc/functions.inc.php#L987):

```php
    $mbox = imap_open ("{dovecot:993/imap/ssl/novalidate-cert}INBOX", $user, $pass);
    if ($mbox != false) {
        imap_close($mbox);
        return "user";
    }
```

As a side-effect, It will also allow logging into mailcow UI using mailcow app passwords (since they are valid for IMAP). **It is not a supported solution with mailcow and has to be done only at your own risk!**

### Two-way sync

Users from your LDAP directory will be added (and deactivated if disabled/not found) to your mailcow database. Not vice-versa, and this is by design.

## Customizations and Integration support

Original tool was created by [Programmierus](https://github.com/Programmierus/LDAP_MAILCOW).
This version is fork from fork by [rinkp](https://github.com/rinkp/custommailcow-ldap)

If you run your mailcow serevr behind Nginx Proxy Manager - you can check [this repo](https://github.com/LazyGatto/npm-cert-export) with additional script to export SSL certificate into mailcow.

**You can always [contact me](mailto:lazygatto@gmail.com) to help you with the integration or for custom modifications on a paid basis. My current hourly rate (ActivityWatch tracked) is 50$ with 3h minimum commitment.**
