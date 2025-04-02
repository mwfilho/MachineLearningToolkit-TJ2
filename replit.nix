{pkgs}: {
  deps = [
    pkgs.wkhtmltopdf
    pkgs.pango
    pkgs.harfbuzz
    pkgs.glib
    pkgs.ghostscript
    pkgs.fontconfig
    pkgs.glibcLocales
    pkgs.postgresql
    pkgs.openssl
  ];
}
