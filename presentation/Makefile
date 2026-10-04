# presentation/ — build recipes
#
#   make demo    theme-demo.pdf   (component test deck)
#   make deck    main.pdf         (clean slides, no notes)
#   make notes   main-notes.pdf   (slides + speaker notes)
#   make all
#   make clean

LATEXMK ?= latexmk
LATEXMKFLAGS ?= -pdf -interaction=nonstopmode -halt-on-error -file-line-error

.PHONY: all demo deck notes clean

all: demo deck notes

demo:
	$(LATEXMK) $(LATEXMKFLAGS) theme-demo.tex

deck:
	$(LATEXMK) $(LATEXMKFLAGS) main.tex

notes:
	$(LATEXMK) $(LATEXMKFLAGS) main-notes.tex

clean:
	$(LATEXMK) -C theme-demo.tex main.tex main-notes.tex 2>/dev/null || true
