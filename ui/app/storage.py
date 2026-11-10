"""How styles and scripts are stored in household mode (milestone 9)."""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class HouseholdStaticStorage(CompressedManifestStaticFilesStorage):
    """WhiteNoise's version-stamped, compressed files, tolerant of libraries' missing extras.

    When preparing the files, every reference inside a CSS or JS file (url(...), source
    maps) is rewritten to the version-stamped name. Some bundled libraries mention files
    they don't ship: Bootstrap's minified script points to a source map (a debugging aid),
    Leaflet's stylesheet to its default marker images (the app draws its own pins).
    Those references are left unchanged instead of stopping the server from starting.
    """

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            if content is None and not self.exists(filename or name):  # a reference to a file that isn't there
                return name
            raise
