# Role Permission Matrix

| Feature | Admin | Manager | Operator | Viewer |
|---|---:|---:|---:|---:|
| Dashboard | yes | yes | yes | yes |
| Detection history | yes | yes | yes | yes |
| Camera list | yes | yes | yes | yes |
| Camera create/update | yes | yes | no | no |
| Camera start/stop | yes | yes | yes | no |
| Camera delete | yes | no | no | no |
| Person list/view | yes | yes | yes | yes |
| Person create/update | yes | yes | yes | no |
| Person bulk import/sync | yes | yes | no | no |
| Person delete | yes | yes | no | no |
| Face image upload | yes | yes | yes | no |
| AI/settings update | yes | no | no | no |
| Appearance (logo/colors) | yes | no | no | no |
| Authentication config (local rules/OIDC/LDAP) | yes | no | no | no |
| Detection schedule update | yes | no | no | no |
| AI provider status view | yes | yes | no | no |
| Greeting template update | yes | yes | no | no |
| User management | yes | no | no | no |
| Audit logs | yes | no | no | no |
