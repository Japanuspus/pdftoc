# pdftoc: A tool for manipulating outlines/table of content (TOC) in pdf files

Add outline to any pdf in one operation based on a single textfile defining the entry hierarchy.
The precise format of the text file can be customized and pdftoc can also read out existing outline.

``` bash
cat some-book-toc.txt
> 1 Introduction . 6
> 2 Background . 10
>     2.1 Previous Work . 13
>     2.2 Our Approach . 15
> 3 Conclusion . 18
pdftoc write some-book.pdf --toc-file some-book-toc.txt
```

Use the TOC file directly or via stdin:

``` bash
pdftoc write some-book.pdf --toc-file some-book-toc.txt
cat some-book-toc.txt | pdftoc write some-book.pdf --toc-file -
pdftoc read some-book.pdf --output -
```

See `pdftoc --help` for details on functionality.

## Install

The single file in `src` works as uv standalone script, alternatively use `uvx`, `uv tool install` or similar

``` bash
uvx --from git+https://github.com/Japanuspus/pdftoc pdftoc -h
```
