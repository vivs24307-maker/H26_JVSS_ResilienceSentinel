from importlib.resources import files

TEMPLATE_NAME = "status.html.j2"


def template_dir():
    return str(files("linkwatch").joinpath("templates"))
