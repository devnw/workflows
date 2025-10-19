{
  description = "dev";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
    dev-env = {
      url = "github:devnw/dev-env";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        unstable.follows = "unstable";
        flake-utils.follows = "flake-utils";
      };
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      dev-env,
      flake-utils,
      ...
    }:
    let
      flakeForSystem =
        nixpkgs: system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          devShell = pkgs.mkShell {
            shellHook = '''';
            env = { };
            packages =
              (with dev-env.packages.${system}; [
                commonPackages
              ])
              ++ (with pkgs; [
              ]);
          };
        };
    in
    flake-utils.lib.eachDefaultSystem (system: flakeForSystem nixpkgs system);

  nixConfig = {
    extra-substituters = [
      "https://oss-devnw.cachix.org"
      "https://oss-spyder.cachix.org"
      "https://oss-codepros.cachix.org"
    ];
    extra-trusted-public-keys = [
      "oss-devnw.cachix.org-1:iJblmQB0mX8MTEqkKJv3piJK3mimEbHpgU1+FSeRuGY="
      "oss-spyder.cachix.org-1:CMypXJpvr7z6IGQdIGDHgZBaZX7JSX9AuPErD/in01g="
      "oss-codepros.cachix.org-1:dP82KzkIxKQp+kS1RgxasR9JYlFdy4W9y7heHeD5h34="
    ];
  };
}
