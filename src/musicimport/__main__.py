import uvicorn

from .config import HOST, PORT


def main() -> None:
    uvicorn.run("musicimport.web.app:app", host=HOST, port=PORT,
                log_level="info", proxy_headers=True)


if __name__ == "__main__":
    main()
