# Contributing to BIDSlab

Thank you for considering contributing to BIDSlab! To improve this package and make it more useful for everyone, your help is needed. This document provides some guidelines for contributing to BIDSlab.

<!-- Need Support? -->

## Found a bug?

The easiest way to contribute is to report a bug. To do so, please open an issue on the [GitHub repository](https://github.com/cimt-unia/BIDSlab/issues).
Please provide as much information as possible, including the version of BIDSlab you are using, the operating system you are using, and the steps to reproduce the bug.
If you find a security vulnerability, do NOT open an issue. Email [cimt@informatik.uni-augsburg.de](mailto:cimt@informatik.uni-augsburg.de) instead.

## Want to suggest a feature?

If you want to suggest a feature to BIDSlab, please open an [issue](https://github.com/cimt-unia/BIDSlab/issues) with a feature request. We will discuss the proposal and decide whether it is a good fit for the package.

## Want to contribute code?

You want to contribute code to BIDSlab? Great! Here is some information to get you started:

1. Have a look at the [open issues](https://github.com/cimt-unia/BIDSlab/issues) or the To-Do list in the [TODO](https://github.com/cimt-unia/BIDSlab/blob/main/TODO) file to see if there is something you would like to work on.
1. Fork the repository and create a new branch for your feature or bug fix.
1. Write your code and tests.
1. Make sure that all tests pass by running `pytest`.
1. Create a pull request to the `dev` branch of the repository.
1. We will review your pull request and provide feedback.
1. Once your pull request is approved, we will merge it into the `dev` branch.
1. The changes on `dev` will be tested and merged into the `main` branch.
1. Your contribution will be part of the next release of BIDSlab!

For more information on the development see the [developer guide](https://bidslab.readthedocs.io/en/latest/developer_guide.html) in the documentation.

## Want to improve the documentation or examples?

You can also contribute to BIDSlab by improving the documentation or examples. To do so, please follow the same steps as for contributing code.
To make sure that your work is not duplicated, please open an issue or pull request to discuss your ideas before you start working on them.
The documentation is built with Sphinx. The homepage, the developer guide and the changelog include the markdown files of the repository (`README.md` and `CHANGELOG.md`) via myst-parser, so please edit those files instead of duplicating their content in the `.rst` files.
The `Changelog.md` file is built automatically.
You can build the documentation locally with `sphinx-build -b html docs/source docs/build/html` as described in the [developer guide](https://bidslab.readthedocs.io/en/latest/developer_guide.html).

## Other questions?

Email the author: [lukas.behammer@uni-a.de](mailto:lukas.behammer@uni-a.de)

## Code of Conduct

Please note that this project is released with a [Contributor Code of Conduct](https://github.com/cimt-unia/BIDSlab/blob/main/CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.
