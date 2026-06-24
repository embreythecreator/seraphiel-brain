# nix/tui.nix — Seraphiel TUI (Ink/React) compiled with tsc and bundled
{ pkgs, seraphielNpmLib, ... }:
let
  npm = seraphielNpmLib.mkNpmPassthru { folder = "ui-tui"; attr = "tui"; pname = "seraphiel-tui"; };

  packageJson = builtins.fromJSON (builtins.readFile (npm.src + "/ui-tui/package.json"));
  version = packageJson.version;
in
pkgs.buildNpmPackage (npm // {
  pname = "seraphiel-tui";
  inherit version;

  doCheck = false;

  buildPhase = ''
    # esbuild bundles everything — no need for tsc or vite.
    # Run from the workspace root where node_modules/ lives.
    node ui-tui/scripts/build.mjs
  '';

  installPhase = ''
    runHook preInstall

    mkdir -p $out/lib/seraphiel-tui
    # esbuild writes to ui-tui/dist/ from the source root (no cd).
    cp -r ui-tui/dist $out/lib/seraphiel-tui/dist

    # package.json kept for "type": "module" resolution on `node dist/entry.js`.
    cp ui-tui/package.json $out/lib/seraphiel-tui/

    runHook postInstall
  '';
})
