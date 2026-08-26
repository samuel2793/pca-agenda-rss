# RSS de la Agenda PCA 2026

Genera un feed RSS 2.0 a partir de:

<https://pca.ua.es/es/agenda/2025/agenda-2026.html>

No necesita servidor propio. **GitHub Actions** descarga y procesa la agenda y **GitHub Pages** publica el resultado estático.

## Qué publica

- `feed.xml`: RSS consumible por Feedly, FreshRSS, Miniflux, NetNewsWire, etc.
- `index.html`: página mínima con enlace al feed y la hora de la última generación.

El parser busca encabezados que parezcan fechas (`11 Sept`, `7-8 Oct`, `10&15 Abr`, `29 Ene - 5 Feb`, etc.), extrae la imagen del cartel cuando aparece antes del enlace del evento y toma el primer enlace de texto del evento antes del siguiente encabezado.

Las imágenes se publican de tres formas para maximizar compatibilidad con lectores RSS:

- `media:content`
- `media:thumbnail`
- `<img>` dentro de `description` y `content:encoded`

Si un evento no tiene imagen en la página de agenda, el elemento RSS se publica normalmente pero sin imagen.

## Puesta en marcha

1. Crea un repositorio en GitHub, por ejemplo `pca-agenda-rss`.
2. Sube el contenido de este directorio a la rama `main`.
3. En GitHub abre **Settings → Pages**.
4. En **Build and deployment → Source**, selecciona **GitHub Actions**.
5. Abre **Actions → Update RSS → Run workflow** para hacer la primera ejecución, o simplemente espera a que la ejecución disparada por el primer `push` termine correctamente.

La URL normal del feed será:

```text
https://TU_USUARIO.github.io/pca-agenda-rss/feed.xml
```

Si el repositorio se llama `TU_USUARIO.github.io`, será:

```text
https://TU_USUARIO.github.io/feed.xml
```

## Frecuencia

`.github/workflows/update-rss.yml` se ejecuta cada hora en el minuto 17 UTC:

```yaml
schedule:
  - cron: "17 * * * *"
```

Puedes cambiarlo. Los cron de GitHub Actions usan UTC y no garantizan ejecución al segundo exacto.

## Por qué existe `keepalive.yml`

GitHub puede desactivar automáticamente los workflows programados de un **repositorio público** cuando no ha habido actividad en el repositorio durante 60 días. Por eso este proyecto incluye un pequeño workflow mensual que actualiza `.github/keepalive` y hace un commit automático.

Si vas a mantener el repositorio activo manualmente o prefieres reactivar el workflow cuando haga falta, puedes eliminar:

```text
.github/workflows/keepalive.yml
.github/keepalive
```

## `pubDate`

El RSS **no inventa `pubDate`**. La página proporciona la fecha de celebración del evento, no la fecha en la que el evento fue publicado en la agenda. Usar la fecha del evento como `pubDate` sería semánticamente incorrecto.

La fecha del evento se incluye en `description` y cada elemento tiene un `guid` estable calculado a partir de año + fecha + título + URL.

## Variables opcionales

Puedes definir variables de entorno en el paso `Generate RSS` si quieres reutilizar el script:

- `PCA_AGENDA_URL`: URL fuente.
- `PCA_AGENDA_YEAR`: año de los eventos (por defecto `2026`).
- `RSS_TITLE`: título del feed.
- `RSS_DESCRIPTION`: descripción del feed.
- `RSS_FEED_URL`: URL pública final del RSS; si se define, se añade un `atom:link rel="self"`.

## Ejecutar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python generate_feed.py
```

Esto crea `site/feed.xml` y `site/index.html`.

## Fallos seguros

Si la web cambia de estructura y el scraper deja de detectar eventos, el proceso termina con error y **no despliega un feed vacío**. Así el último RSS válido permanece publicado en Pages hasta que se adapte el parser.
