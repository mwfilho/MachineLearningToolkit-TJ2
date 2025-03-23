{pkgs}: {
  deps = [
    pkgs.wkhtmltopdf
    pkgs.glibcLocales
    pkgs.postgresql
    pkgs.openssl
  ];
}
