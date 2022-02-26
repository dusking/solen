import re
import logging
import configparser
from configparser import _UNSET, NoSectionError

from asyncit.dicts import DotDict

logger = logging.getLogger(__name__)


class ConfigParser(configparser.ConfigParser):  # pylint: disable=too-many-ancestors
    def __init__(self, config_file=None):
        self.config_file = config_file
        super().__init__()

    def options(self, section, include_defaults=True):  # pylint: disable=arguments-differ
        """Return a list of option names for the given section name.

        :param section: the section to get options for.
        :param include_defaults: The section DEFAULT is special. Add default values as values for the section.
        """
        if not include_defaults:
            try:
                return list(self._sections[section].keys())
            except KeyError as ex:
                raise NoSectionError(section) from ex
        else:
            return super().options(section)

    def sections(self):
        return list(self._sections.keys())

    def section(self, section, include_defaults=True):
        items = self.items(section, include_defaults)
        return DotDict(dict(items))

    def items(
        self, section=_UNSET, raw=False, vars=None, include_defaults=True
    ):  # pylint: disable=redefined-builtin, arguments-differ
        """Return a list of (name, value) tuples for each option in a section.

        :param section: the section to get items for.
        :param raw: All % interpolations are expanded in the return values, based on the
            defaults passed into the constructor, unless the optional argument
            `raw' is true.
        :param vars: Additional substitutions may be provided using the
            `vars' argument, which must be a dictionary whose contents overrides
            any pre-existing defaults.
        :param include_defaults: The section DEFAULT is special. Add default values as values for the section.
        """
        if section is _UNSET:
            return super().items()
        if include_defaults:
            data = self._defaults.copy()
        else:
            data = {}
        try:
            if section in self._sections:
                data.update(self._sections[section])
            elif section.upper() in self._sections:
                data.update(self._sections[section.upper()])
        except KeyError as ex:
            if section != self.default_section:
                raise NoSectionError(section) from ex
        # Update with the entry specific variables
        if vars:
            for key, value in vars.items():
                data[self.optionxform(key)] = value
        value_getter = lambda option: self._interpolation.before_get(self, section, option, data[option], data)
        if raw:
            value_getter = lambda option: data[option]
        return [(option, value_getter(option)) for option in data.keys()]

    def optionxform(self, optionstr):
        return self.camel_case_to_snake(optionstr)

    def camel_case_to_snake(self, name):
        pattern = re.compile(r"(?<!^)(?=[A-Z])")
        name = pattern.sub("_", name).lower()
        return name

    def get_value(self, section, key, default=None):
        try:
            return self[section][key]
        except Exception as ex:
            if default:
                return default
            sections = self.sections()
            if section in sections:
                items = self.items(section)
            else:
                items = []
            logger.info(f"get_config_value: failed on - {section}/{key}. sections: {sections}, section items: {items}")
            raise Exception(f"missing config key: {section}/{key}") from ex

    def auto_attr(self):
        for section in self.sections():
            setattr(self, section.lower(), self.section(section))

    def load(self, config_file=None):
        self.read(str(config_file) if config_file else self.config_file)
        self.auto_attr()
