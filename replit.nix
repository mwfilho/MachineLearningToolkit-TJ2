{pkgs}: {
  deps = [
    pkgs.python3
    pkgs.wkhtmltopdf
    pkgs.jq
    pkgs.glibcLocales
    pkgs.postgresql
    pkgs.openssl
  ];
}
