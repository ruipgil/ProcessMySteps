all: compile

compile: clean
	pyinstaller --onefile .spec

clean:
	rm -fr dist build
