{pkgs}: {
  deps = [
    pkgs.zlib
    pkgs.xcodebuild
    pkgs.jq
    pkgs.glibcLocales
    pkgs.postgresql
    pkgs.openssl
  ];
}
