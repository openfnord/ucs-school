[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# UCS@school

Welcome to the git mirror of UCS@school.
[UCS@school](https://www.univention.com/products/ucsschool/) is a
comprehensive solution to provide access to infrastructure and
applications in schools as well as a complete toolset to operate them.
It can be used in an individual school but it is best suited for school
districts or school authorities centrally managing infrastructure for
tens or hundreds of schools. It is used by a number of larger school
authorities in Germany.

## Download

UCS@school requires Univention Corporate Server (UCS). In order to run UCS@school:

1. [Download](https://www.univention.com/products/download/) either an ISO image or a virtual machine image of UCS and setup UCS.
2. Login to the UCS management system and open the App Center and install the [UCS@school app](https://www.univention.de/produkte/univention-app-center/app-katalog/ucsschool/).

## Run pre-commit locally

This project uses pre-commit to run checks on commits. The pipeline has a pre-commit job. To run the checks prior to push, you can run the following command from the project's root directory:

```
docker run -it --rm -v "$PWD:/project" -w /project --pull always gitregistry.knut.univention.de/univention/ucsschool:latest
```

For running pre-commit outside of docker, you will need the following python versions installed:

* python3.7
* python3.8

*Hint*: if you run into issues running pre-commit with multiple python versions installed, you may need to install pre-commit as a python library using pip, for each python version. Be sure to close and re-open your terminal before running pre-commit again.


## Documentation and Support

The UCS@school documentation, including a Quickstart guide, can be found at [docs.software-univention.de](https://docs.software-univention.de/) .

If you need direct help, the forum [Univention
Help](https://help.univention.com) provides a very good community support. For
commercial support, please have a look at our [support
offerings](https://www.univention.com/download-and-support/support/commercial-support/).

## Contributing

Please read the [contributing guide](./CONTRIBUTING.md) to find more information about the UCS@school development process, how to propose bugfixes and improvements.
The [Code of Conduct contains guidelines](./CONTRIBUTING.md#code-of-conduct) we expect project participants to adhere to.

## License

The source code of UCS@school is licensed under the AGPLv3. Please see the [license file](./LICENSE) for more information.
