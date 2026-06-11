# pdftoc: A tool for manipulating outlines/table of content (TOC) in pdf files

Add outline to any pdf in one operation based on a single textfile defining the entry hierarchy.
The precise format of the text file can be customized and pdftoc can also read out existing outline.

``` bash
cat some-book-toc.txt
> ---
> Offset: 5
> ---
>  3 1 Introduction
>  7   1.1 Why this book
pdftoc add some-book.pdf
```

See `pdftoc help` for details on functionality.

## Install

``` bash
uv tool install ....
```
