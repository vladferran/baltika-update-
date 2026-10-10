.PHONY: install test run lint deploy logs

install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

test:
	python3 -m pytest tests -q

run:
	python3 -m app.bot

deploy:
	rsync -av --exclude-from=.gitignore --exclude .git ./ root@SERVER:/opt/baltika_bot/
	ssh root@SERVER 'systemctl restart baltika-bot'

logs:
	ssh root@SERVER 'journalctl -u baltika-bot -f'
