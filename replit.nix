{pkgs}: {
  deps = [
    pkgs.pdftk
    pkgs.wkhtmltopdf
    pkgs.pango
    pkgs.harfbuzz
    pkgs.glib
    pkgs.ghostscript
    pkgs.fontconfig
    pkgs.freetype
    pkgs.jq
    pkgs.glibcLocales
    pkgs.postgresql
    pkgs.openssl
  ];
}
