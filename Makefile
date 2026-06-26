CALIBRE   := /Applications/calibre.app/Contents/MacOS
PLUGIN    := calibre_plugin

ifneq ($(shell uname),Darwin)
$(error install/reload targets are macOS-only. Run 'python build.py' to build the zip on other platforms.)
endif

.PHONY: install kill reload dist test

install:
	$(CALIBRE)/calibre-customize -b $(PLUGIN)

kill:
	pkill -9 calibre 2>/dev/null || true
	@while pgrep -q calibre 2>/dev/null; do sleep 0.2; done

reload: install kill
	open -a calibre

dist:
	python build.py

test:
	python -m pytest tests/ -q
