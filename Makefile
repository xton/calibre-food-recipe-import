CALIBRE   := /Applications/calibre.app/Contents/MacOS
PLUGIN    := calibre_plugin

.PHONY: install kill reload test

install:
	$(CALIBRE)/calibre-customize -b $(PLUGIN)

kill:
	pkill -9 calibre 2>/dev/null || true
	@while pgrep -q calibre 2>/dev/null; do sleep 0.2; done

reload: install kill
	open -a calibre

test:
	python -m pytest tests/ -q
