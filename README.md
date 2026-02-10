# `hopsworks-apigen`

This project is a collection of plugins and extensions for building Hopsworks Python API package, [`hopsworks`](https://pypi.org/project/hopsworks/), and its [docs](https://docs.hopsworks.ai/latest/python-api/).

The main purpose of these extensions is to support a clear demarcation of the public API and its deprecated parts.
By doing this, the package enables Hopsworks developers to change the API gradually, maintaining backward compatibility while steadily improving it.

## Usage

### Generating Aliases

If you want to generate an alias for a class or a function, firstly think if you can avoid doing it.
In case you have to do it to maintain backwards-compatibility, you can use the `@also_available_as` decorator, which takes the new member path as an argument:

```python
@also_available_as("hopsworks.client.exceptions.RestAPIError")
class RestAPIError(Exception):
    ...
```

### Marking API Members as Public

If you want to mark a class or a function as public, you can use the `@public` decorator:

```python
@public
class FeatureGroup:
    ...
```

You can also generate public aliases, which are mentioned in the docs.
As with internal aliases, you should seriously think if you can avoid doing it; but if you have to do it to maintain backwards-compatibility, you can use the `@public` decorator with the paths of the aliases as arguments.
In this case, the first path argument of `@public` is the canonical member path, and the rest are mentioned in a special "Aliases" section in the docs.
The current path is to be marked as an empty string, `""`.

```python
# The canonical path is the current path, and two public aliases are created:
@public("", "hopsworks.FeatureGroup", "hsfs.feature_group.FeatureGroup")
class FeatureGroup:
    ...

# The canonical path is "hopsworks.RestAPIError", while the current path is hidden from the docs:
@public("hopsworks.RestAPIError")
class RestAPIError(Exception):
    ...
```

### Deprecating API Members

If you want to deprecate a function, you have to use `@deprecated` decorator, which takes the recommended alternative member paths as arguments.
You should only use it on public members.
Make sure to use `@deprecated` above `@public`, so that the correct meta-information is shown to the user in the deprecation warning.

```python
# Nothing should be removed in a patch release, so major.minor version is used to specify the release in which the method is to be removed.
# Here we say that the users should use `isin` instead of `contains`, and that `contains` is to be removed in 5.0:
@deprecated("hopsworks.Feature.isin", available_until="5.0")
@public
def contains(self, other: str | list[Any]) -> filter.Filter:
    ...

# In case we don't know yet the exact release in which the method is to be removed, we can omit it:
@deprecated("hopsworks.Feature.isin")
@public
def contains(self, other: str | list[Any]) -> filter.Filter:
    ...
```

## Background

Historically it so happened that in the Hopsworks Python API package, there was no clear distinction between the public API and the internal implementation.
Although some efforts to use the Python convention of prefixing internal members with an underscore were made, it was not consistently applied across the codebase.
This lack of a clear demarcation led to confusion among users and developers alike, as it was not always clear which parts of the API were intended for public use and which were meant for internal use only.
This situation made it difficult to maintain backward compatibility while making necessary changes and improvements to the API, as there was no clear way to deprecate internal members without affecting users who might have been using them.

Moreover, before 4.0, the Hopsworks Python API was split across three separate tightly coupled packages, [hopsworks-api](https://github.com/logicalclocks/hopsworks-api), [feature-store-api](https://github.com/logicalclocks/feature-store-api), and [machine-learning-api](https://github.com/logicalclocks/machine-learning-api).
Originally the package structure was the same across these packages, but they slowly diverged.
Also, some code was duplicated and even triplicated, and the API behaviour was not totally consistent across the packages.
Especially problematic was the problem of catching API exceptions, as the same exception classes were defined in all three packages.
In the end, the users had to import the same exception classes from three different packages, like here:

```python
from hopsworks.client.exceptions import RestAPIError as HopsworksRestAPIError
from hsfs.client.exceptions import RestAPIError as FeatureStoreRestAPIError
from hsml.client.exceptions import RestAPIError as MachineLearningRestAPIError

try:
    # Use the API
except (HopsworksRestAPIError, FeatureStoreRestAPIError, MachineLearningRestAPIError) as e:
    # Handle the exception
```

In 4.0, the Hopsworks Python API was unified into a single package, `hopsworks`, which contains all the functionality of the previous three packages.
Aliases were manually created to maintain backward compatibility, so that users could still import the same classes and functions from the same locations as before, while the internal implementation was unified.
So instead of importing the same exception classes from three different packages, users could now import them from the unified package, like here:

```python
from hopsworks.client.exceptions import RestAPIError

try:
    # Use the API
except RestAPIError as e:
    # Handle the exception
```

This unification was a significant step towards improving the consistency and usability of the API, as it deduplicated the API and unified the behavior of the API methods.
However, the issue of distinguishing between the public API and internal implementation still remained, as there was no clear way to mark certain members as internal or deprecated, slowing down the development process and confusing the users.
Moreover, the structural inconsistencies between the previous three packages were still present in the unified package, making it difficult to navigate and understand.

## Solution

To address these issues, the `hopsworks-apigen` project was created to provide a clear demarcation of the public API and its deprecated parts, as well as to ease the maintenance of the backwards-compatibility aliases in the API.

### Generation of Aliases

As a result of the deduplication and unification of the API, many classes and functions were moved to different locations in the package, and some of them were renamed.
To maintain backward compatibility, aliases were created for all the moved and renamed members, so that users could still import them from the same locations as before.
Manual creation of these aliases is a tedious and error-prone process, so `hopsworks-apigen` automates it.

It is done by providing a `setuptools` plugin, which generates all the aliases based on `@also_available_as` and `@public` decorators during the package building process.

### Marking the Public API

Since in our API we failed to rigorously follow [PEP8](https://peps.python.org/pep-0008/), which recommends prefixing internal members with an underscore, we need another way to mark the public API.

To do this, `hopsworks-apigen` provides a `@public` decorator, which can be used to mark the public API members.
This decorator does not change the behavior of the decorated members, but it serves as a marker for both the developers and the users of what is public in the API and what is not (even if it is not named with an underscore in the beginning).

### Deprecation Mechanism

We also had no clear way to deprecate API members.

To mark the deprecated API, `hopsworks-apigen` provides a `@deprecated` decorator, which can be used to mark the deprecated API members.
Usage of such members will raise a `HopsworksDeprecationWarning`, which informs the users about the deprecation and encourages them to migrate to the recommended alternatives.

### API Reference Generation

Finally, `hopsworks-apigen` provides a `mkdocs` plugin for generating the API reference documentation, making everything marked as public appear in the documentation.
Therefore, the documentation is ensured to be complete and consistent with the use of `@public`.

## Moving Forward

This repository is not meant to stay coupled with the Hopsworks Python API forever, but it is meant to be a temporary solution to support the transition period of the API unification and improvement.
Once the API is fully unified and PEP8-compliant, there will be no longer need for `hopsworks-apigen`.

So, `hopsworks-apigen` is to be removed once:

- PEP8 underscores naming convention is properly followed throughout the codebase;
- Unification of the API is completed, so that there is a clear structure of the package and no more inconsistencies;
- The backwards-compatibility aliases are no longer needed, by gradually deprecating and removing them.

After it is removed, the API reference generation can be done with [`mkdocs-api-autonav`](https://github.com/tlambert03/mkdocs-api-autonav), and the `@deprecated` decorator can be moved into the Python API repository.
There should be no need in `@also_available_as` decorator, as there should be no more need for aliases, and there should be no need in `@public` decorator since PEP8 conventions should be rigorously followed at this point.
