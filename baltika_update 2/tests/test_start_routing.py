"""/start должен доходить до онбординга, а не перехватываться меню."""

from app import menu


def _command_names(router) -> set[str]:
    names: set[str] = set()
    for handler in router.message.handlers:
        for flt in handler.filters:
            cmds = getattr(flt.callback, "commands", None)
            for c in cmds or ():
                names.add(str(getattr(c, "command", c)).lower())
    return names


def test_menu_router_does_not_take_start():
    assert "start" not in _command_names(menu.router)
    assert "menu" in _command_names(menu.router)
