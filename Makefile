.PHONY: installdeps run install_as_system_service

installsysdeps:
	sudo apt-get install pipenv
	#sudo apt-get install python3-apscheduler
	#sudo apt-get install python3-pylint-common

installdeps:
	PIPENV_VENV_IN_PROJECT=1 pipenv --python python3
	pipenv install flask apscheduler requests

installservice:
	cp Pipfile* ~/run/GitToDo
	cp scripts/GitToDo.service ~/run/GitToDo
	PIPENV_VENV_IN_PROJECT=1 pipenv sync
	#systemctl link ~/run/GitToDo/

run:
	pipenv run python3 ./main.py

restartservice:
	sudo systemctl restart GitToDo.service && journalctl -f -u GitToDo.service

lint.log: *.py
	autopep8 -r --in-place --aggressive --aggressive . | tee lint.log
	python3 -m pylint *.py --disable=C0411 | tee --append lint.log

