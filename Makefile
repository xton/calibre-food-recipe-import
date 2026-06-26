CALIBRE   := /Applications/calibre.app/Contents/MacOS
PLUGIN    := calibre_plugin

.PHONY: install kill reload test

install:
	$(CALIBRE)/calibre-customize -b $(PLUGIN)

kill:
	pkill -x calibre || true

reload: install kill
	open -a calibre

test:
	python -m pytest tests/ -q
