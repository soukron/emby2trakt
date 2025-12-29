# Configuración de Traefik

Traefik está configurado como proxy reverso con soporte para Let's Encrypt.

## Configuración Actual

### Dominio
- **Dominio del webhook**: `trakt-webhook.gmbros.net`
- **IP del servidor**: `217.13.82.45`
- **Email Let's Encrypt**: `admin@gmbros.net`

### Servidor Emby
- **Dominio**: `sniperembyp7p8.zapto.org`
- **IP permitida**: `195.201.196.25/32` (configurada en IP whitelist)

## Requisitos

1. **DNS configurado**: El dominio `trakt-webhook.gmbros.net` debe apuntar a la IP `217.13.82.45`
2. **Puertos abiertos**: Los puertos 80 y 443 deben estar accesibles desde Internet (configurados en firewall)
3. **Email válido**: El email se usa para notificaciones de Let's Encrypt

## Dashboard de Traefik

El dashboard de Traefik está disponible en `http://172.25.55.60:8080`.

Desde el dashboard puedes:
- Ver routers configurados
- Ver servicios detectados
- Ver middlewares activos
- Ver certificados SSL
- Ver métricas y logs

## Funcionalidades Implementadas

### Proxy Reverso
- ✅ Proxy reverso automático con auto-discovery de contenedores Docker
- ✅ Configurado para el dominio `trakt-webhook.gmbros.net`
- ✅ Enruta el tráfico HTTPS al contenedor `trakt-webhook-server` en el puerto 5000

### Certificados SSL
- ✅ Certificados SSL automáticos con Let's Encrypt
- ✅ Renovación automática de certificados
- ✅ Redirección HTTP → HTTPS automática
- ✅ Certificados almacenados en volumen `traefik-certificates`

### Seguridad
- ✅ **IP Whitelist**: Solo permite peticiones desde la IP del servidor Emby (`195.201.196.25`)
  - Middleware: `webhook-ipwhitelist`
  - Bloquea todo el tráfico no autorizado antes de llegar a la aplicación

### Observabilidad
- ✅ **Accesslog**: Registro de todas las peticiones HTTP
  - Formato: `common` (legible)
  - Los logs se pueden ver con: `docker logs -f traefik`
  - Registra: IP origen, método HTTP, ruta, código de respuesta, tiempo de respuesta, etc.

## Configuración del Webhook

El contenedor `trakt-webhook-server` está configurado con las siguientes labels de Traefik:

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.webhook.rule=Host(`trakt-webhook.gmbros.net`)"
  - "traefik.http.routers.webhook.entrypoints=websecure"
  - "traefik.http.routers.webhook.tls.certresolver=letsencrypt"
  - "traefik.http.services.webhook.loadbalancer.server.port=5000"
  - "traefik.http.routers.webhook.middlewares=webhook-ipwhitelist"
  - "traefik.http.middlewares.webhook-ipwhitelist.ipwhitelist.sourcerange=195.201.196.25/32"
```

## Comandos Útiles

### Ver logs de Traefik
```bash
# Ver logs en tiempo real
docker logs -f traefik

# Ver últimas 50 líneas
docker logs --tail 50 traefik

# Ver solo accesslogs (filtrar logs de info)
docker logs traefik 2>&1 | grep -v "level=info"
```

### Verificar configuración
```bash
# Ver routers configurados
curl http://172.25.55.60:8080/api/http/routers | python3 -m json.tool

# Ver middlewares configurados
curl http://172.25.55.60:8080/api/http/middlewares | python3 -m json.tool

# Ver servicios detectados
curl http://172.25.55.60:8080/api/http/services | python3 -m json.tool
```

### Reiniciar servicios
```bash
# Reiniciar Traefik
docker compose up -d traefik

# Reiniciar webhook
docker compose up -d trakt-webhook-server

# Reiniciar todo
docker compose up -d
```

## Estructura de la Configuración

```
traefik/
├── Proxy reverso
│   ├── Entrypoint HTTP (puerto 80) → Redirige a HTTPS
│   └── Entrypoint HTTPS (puerto 443) → SSL/TLS
├── Certificados
│   ├── Let's Encrypt (renovación automática)
│   └── Almacenados en volumen traefik-certificates
├── Middlewares
│   └── IP Whitelist (solo IP del servidor Emby)
└── Observabilidad
    └── Accesslog (formato common)
```

## Notas Importantes

1. **IP Whitelist**: Solo el servidor Emby (`195.201.196.25`) puede acceder al webhook. Cualquier otra IP recibirá un error 403 Forbidden.

2. **Accesslog**: Los logs se escriben a stdout del contenedor. Para persistirlos, considera configurar un driver de logging de Docker o un sistema de logging centralizado.

3. **Certificados**: Los certificados SSL se renuevan automáticamente. El volumen `traefik-certificates` almacena el archivo `acme.json` con los certificados.

4. **Dashboard**: El dashboard está accesible en `172.25.55.60:8080` sin autenticación. Si necesitas más seguridad, considera añadir autenticación básica.

## Troubleshooting

### El certificado SSL no se genera
- Verifica que el DNS apunta correctamente a `217.13.82.45`
- Verifica que los puertos 80 y 443 están abiertos en el firewall
- Revisa los logs: `docker logs traefik`

### El webhook no recibe peticiones
- Verifica que el contenedor está corriendo: `docker compose ps`
- Verifica que la IP del servidor Emby está en la whitelist
- Revisa los accesslogs: `docker logs traefik`

### Error 403 Forbidden
- Verifica que la IP del servidor Emby (`195.201.196.25`) está configurada correctamente en el IP whitelist
- Verifica que el servidor Emby está enviando peticiones desde esa IP
