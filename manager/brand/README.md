# brand/

The logo and tab icon of the console, named in `.env` by `MANAGER_BRAND_LOGO`
and `MANAGER_BRAND_FAVICON` and served at `/brand/<file>` (svg, png, jpg, webp
or ico). Only the two files named are served.

The repository ships SIPMediaGW's own, taken from the upstream repository:

- `logo.svg`: the SIPMediaGW wordmark (`browsing/assets/IVR/logo.svg`);
- `favicon.svg`: its key, squared for a tab (`deploy/proxyAPI/favicon.svg`).

A deployment adds its own files here — they stay out of git — and names them:

    cp /path/to/my-logo.png /path/to/my-icon.png brand/
    # .env
    MANAGER_BRAND_NAME=My Service Manager
    MANAGER_BRAND_LOGO=my-logo.png
    MANAGER_BRAND_FAVICON=my-icon.png   # square; empty: the tab shows the logo

The logo is shown 34 px high, width following (160 px at most). With
docker-compose.prod.yml the directory is mounted read-only into the container;
with docker-compose.yml the whole source is.
