# Emby to Trakt Webhook

Servicio webhook que recibe eventos de reproducción de Emby y registra automáticamente los episodios vistos en Trakt.

## Descripción

Este servicio actúa como intermediario entre Emby y Trakt:
- Recibe webhooks de Emby cuando se reproduce un episodio
- Procesa los eventos de reproducción
- Registra automáticamente los episodios vistos en Trakt cuando se completa la reproducción (≥80%)

## Requisitos

- Python 3.8 o superior
- Cuenta de Trakt
- Servidor Emby con webhooks habilitados (requiere Emby Premiere)

## Instalación

1. Clona o descarga este repositorio

2. Crea un entorno virtual (recomendado):
```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instala las dependencias:
```bash
pip install -r requirements.txt
```

4. Obtén las credenciales de Trakt:
   - Ve a https://trakt.tv/oauth/applications
   - Crea una nueva aplicación
   - Copia el `Client ID` y `Client Secret`
   - Para obtener el `Access Token`, necesitarás autenticarte con OAuth (ver sección de autenticación)

5. Configura las variables de entorno:
```bash
cp .env.example .env
# Edita .env con tus credenciales
```

O exporta las variables directamente:
```bash
export TRAKT_CLIENT_ID="tu_client_id"
export TRAKT_CLIENT_SECRET="tu_client_secret"
export TRAKT_ACCESS_TOKEN="tu_access_token"
```

## Autenticación con Trakt

Para obtener el `TRAKT_ACCESS_TOKEN`, necesitas autenticarte con OAuth. Puedes usar el script `get_trakt_token.py`:

```bash
python get_trakt_token.py
```

Este script te guiará a través del proceso de autenticación OAuth y obtendrá el token de acceso.

## Configuración en Emby

1. Ve a la configuración de tu servidor Emby
2. Navega a **Webhooks** (requiere Emby Premiere)
3. Crea un nuevo webhook con la siguiente configuración:
   - **URL**: `http://tu-servidor:5000/webhook`
   - **Eventos**: Selecciona al menos:
     - `playback.start`
     - `playback.stop`
     - `playback.progress`

## Ejecución

### Desarrollo

Asegúrate de tener el entorno virtual activado:
```bash
source venv/bin/activate  # En Windows: venv\Scripts\activate
python app.py
```

### Producción
Para producción, se recomienda usar un servidor WSGI como Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

O con systemd (ver sección de systemd service)

## Endpoints

- `GET /` - Información del servicio
- `GET /health` - Verificación de salud del servicio
- `POST /webhook` - Endpoint que recibe los webhooks de Emby

## Funcionamiento

1. Cuando reproduces un episodio en Emby, este envía un webhook al servicio
2. El servicio verifica que sea un episodio de serie (no película)
3. Cuando la reproducción alcanza el 80% o se detiene, el episodio se marca como visto en Trakt
4. El servicio busca la serie en Trakt por nombre o ID externo (TMDB/TVDB)
5. Registra el episodio en tu historial de Trakt

## Logs

El servicio registra todas las operaciones. Puedes ver los logs en la consola o redirigirlos a un archivo:

```bash
python app.py >> webhook.log 2>&1
```

## Solución de problemas

### El servicio no recibe webhooks
- Verifica que Emby tenga webhooks habilitados (requiere Premiere)
- Verifica que la URL del webhook sea accesible desde el servidor Emby
- Revisa los logs del servicio

### Los episodios no se registran en Trakt
- Verifica que las credenciales de Trakt estén correctas
- Verifica que el episodio tenga suficiente progreso (≥80%)
- Revisa los logs para ver errores específicos
- Verifica que la serie exista en Trakt

### Error de autenticación con Trakt
- Verifica que el `TRAKT_ACCESS_TOKEN` sea válido
- Si el token expiró, necesitarás obtener uno nuevo

## Notas

- El servicio solo procesa episodios de series, no películas
- Los episodios se registran cuando se completa al menos el 80% de la reproducción
- El servicio busca series en Trakt por nombre o ID externo (TMDB/TVDB/IMDB)

## Licencia

Este proyecto es de código abierto y está disponible para uso personal.

