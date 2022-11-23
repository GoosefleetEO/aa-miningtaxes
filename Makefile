appname = aa-miningtaxes
package = miningtaxes

help:
	@echo "Makefile for $(appname)"

tx_push:
	tx push --source

tx_pull:
	tx pull -f

publish:
	rm -f dist/*
	python setup.py sdist
	twine upload dist/*

compilemessages:
	cd $(package) && \
	django-admin compilemessages -l en  && \
	django-admin compilemessages -l de  && \
	django-admin compilemessages -l es  && \
	django-admin compilemessages -l ko  && \
	django-admin compilemessages -l ru  && \
	django-admin compilemessages -l zh_Hans

coverage:
	coverage run ../manage.py test $(package).tests --keepdb --failfast && coverage html && coverage report -m

test:
	# runs a full test incl. re-creating of the test DB
	python ../manage.py test $(package) --failfast --debug-mode -v 2

pylint:
	pylint --load-plugins pylint_django $(package)

check_complexity:
	flake8 $(package) --max-complexity=10

nuke_testdb:
	# This will delete the current test database
	# very userful after large changes to the models
	sudo mysql -u root -e "drop database test_aa_dev_4;"

flake8:
	flake8 $(package) --count
