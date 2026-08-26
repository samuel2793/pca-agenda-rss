# PCA Agenda RSS

RSS no oficial de la agenda del Parque Científico de Alicante.

Convierte automáticamente la agenda publicada en:

https://pca.ua.es/es/agenda/2025/agenda-2026.html

en un feed RSS actualizado mediante GitHub Actions y publicado con GitHub Pages.

## Feed

```text
https://samuel2793.github.io/pca-agenda-rss/feed.xml
```

## Qué incluye

* Eventos de la agenda del PCA
* Fecha y título
* Enlace al evento original
* Imagen del evento cuando está disponible
* Actualización automática

## Cómo funciona

GitHub Actions consulta periódicamente la agenda, genera `feed.xml` y lo publica en GitHub Pages.

No requiere servidor propio ni servicios externos.

## Uso

Añade la URL del feed a cualquier lector RSS compatible, por ejemplo:

* FreshRSS
* Miniflux
* Feedly
* NetNewsWire
* Reeder

## Ejecutarlo localmente

```bash
pip install -r requirements.txt
python generate_feed.py
```

## Aviso

Proyecto no oficial y no afiliado con la Universidad de Alicante ni con el Parque Científico de Alicante.

El feed depende de la estructura de la página original, por lo que podría dejar de funcionar si esta cambia.
