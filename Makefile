.PHONY: installdeps run install_as_system_service

installdeps:
	sudo apt-get install python3-apscheduler
	sudo apt-get install python3-pylint-common

run:
	python3 ./main.py

lint.log: *.py
	autopep8 -r --in-place --aggressive --aggressive . | tee lint.log
	python3 -m pylint *.py --disable=C0411 | tee --append lint.log

install_as_system_service:
	./scripts/install_as_system_service.sh
