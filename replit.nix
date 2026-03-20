{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.redis
    pkgs.stdenv.cc.cc.lib
  ];
}
