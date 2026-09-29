#!/usr/bin/env python3
"""Maintainer helper: refresh the focused Mac overlay from an audited source checkout.

Not used by the installer. Source is an explicit argument, never a machine-local
implicit dependency. Review every refreshed diff and revalidate the build.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'port/android/README.md','port/android/app/src/main/java/com/halo/decomp/LauncherActivity.java','port/android/host/host_gl.c'}
OPTIONAL_MAC_FILES=set()
TOOLS=('macos_aot_build.py','macos_import_stubs.py','macos_lift_elf.py','macos_gl_bridge.py','macos_package_app.py','check_macos_symbol_namespaces.py','test_macos_symbol_namespaces.py','test_macos_network_startup.py','test_macos_multiplayer_harness.py','test_macos_display_cycle.py','test_macos_hd_resolution.py','test_macos_sdl_window.py')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    args=parser.parse_args();src=args.source.resolve();runtime=args.runtime.resolve()
    pins=json.loads((ROOT/'pins.json').read_text());base=pins['halo']['commit']
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',base],cwd=src,text=True).splitlines()
    patch=[]
    for rel in paths:
        if rel in EXCLUDE or not rel.startswith(('source/','port/linux/','port/android/','port/include/')):continue
        current=src/rel
        if not current.is_file():continue
        old=subprocess.check_output(['git','show',base+':'+rel],cwd=src)
        new=current.read_bytes()
        if old==new:continue
        patch.extend(difflib.unified_diff(old.decode().splitlines(keepends=True),new.decode().splitlines(keepends=True),fromfile='a/'+rel,tofile='b/'+rel))
    (ROOT/'patches/macos-source.patch').write_text(''.join(patch))
    # Retain public packaging and portability adjustments rather than silently
    # replacing them with private development defaults.
    for path in (src/'port/macos').iterdir():
        if path.suffix in ('.c','.h','.m','.ld') and path.name not in OPTIONAL_MAC_FILES:
            target=ROOT/'overlay/port/macos'/path.name
            if path.name=='main.c':
                code=path.read_text()
                import re
                code=re.sub(r'char default_data_root\[\] = "[^"]*";', 'char default_data_root[] = ".";', code)
                target.write_text(code)
            else:shutil.copy2(path,target)
    for name in TOOLS:
        if name!='macos_package_app.py':shutil.copy2(src/'tools'/name,ROOT/'overlay/tools'/name)
    controller=(src/'tools/test_macos_gamepad.py').read_text()
    controller=controller.replace('No game is launched. --candidate tests isolated unpublished controller changes.',
                                  'No game is launched; virtual devices exercise mappings without physical hardware.')
    start=controller.index(" p=argparse.ArgumentParser();")
    end=controller.index(" text=src.read_text();",start)
    controller=controller[:start]+" p=argparse.ArgumentParser();p.parse_args()\n src=ROOT/'port/linux/src/xinput_sdl.c'\n host=ROOT/'port/macos/host_sdl.c'\n"+controller[end:]
    if 'void mac_game_evidence_presented(void)' not in controller:
        controller=controller.replace('void mac_host_activate_app(void){}', 'void mac_host_activate_app(void){}\nvoid mac_game_evidence_presented(void){}')
    (ROOT/'overlay/tools/test_macos_gamepad.py').write_text(controller)
    translated=(src/'tools/test_macos_translated_gamepad.py').read_text()
    translated=translated.replace("p.add_argument('--reuse-lift',action='store_true')", "p.add_argument('--recomp-root',type=Path,required=True);p.add_argument('--reuse-lift',action='store_true')")
    translated=translated.replace("str(ROOT/'tools/dependencies/xboxrecomp-runtime-overlay')", "str(a.recomp_root)")
    (ROOT/'overlay/tools/test_macos_translated_gamepad.py').write_text(translated)
    errno=(src/'tools/test_macos_translated_errno.py').read_text()
    errno=errno.replace("p.add_argument('--miniupnpc-lib',type=Path,required=True)", "p.add_argument('--miniupnpc-lib',type=Path,required=True);p.add_argument('--recomp-root',type=Path,required=True)")
    errno=errno.replace("str(ROOT/'tools/dependencies/xboxrecomp-runtime-overlay')", "str(a.recomp_root)")
    (ROOT/'overlay/tools/test_macos_translated_errno.py').write_text(errno)
    pair=(src/'tools/run_macos_multiplayer_pair.py').read_text()
    if 'from macos_network_test_lock import acquire_network_test_lock' not in pair:
        pair=pair.replace('ROOT=Path(__file__).resolve().parents[1]', 'from macos_network_test_lock import acquire_network_test_lock\nROOT=Path(__file__).resolve().parents[1]')
    if 'acquire_network_test_lock()' not in pair:
        pair=pair.replace(" if a.check_only:print(json.dumps(runs,indent=2));return 0\n", " if a.check_only:print(json.dumps(runs,indent=2));return 0\n try:network_lease=acquire_network_test_lock()\n except RuntimeError as error:p.error(str(error))\n")
    (ROOT/'overlay/tools/run_macos_multiplayer_pair.py').write_text(pair)
    # These original host fixtures follow native source changes. The bounded
    # supervisor and controller test scripts retain their public CLI adjustments.
    for path in (src/'port/macos/tests').iterdir():
        if path.suffix in ('.c', '.h', '.inc') and path.name not in OPTIONAL_MAC_FILES:
            target=ROOT/'overlay/port/macos/tests'/path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(''.join(line.rstrip()+ '\n' for line in path.read_text().splitlines()))
    for name in ('input_bindings.c','input_bindings.h'):
        shutil.copy2(src/'port/linux/src'/name,ROOT/'overlay/port/linux/src'/name)
    # CMake may add native sources; retain the explicit deployment/test defaults.
    cmake=(src/'port/macos/CMakeLists.txt').read_text()
    if 'CMAKE_OSX_DEPLOYMENT_TARGET' not in cmake:
        cmake=cmake.replace('project(HaloMacOSSourceAOT LANGUAGES C OBJC)','if(NOT DEFINED CMAKE_OSX_DEPLOYMENT_TARGET)\n  set(CMAKE_OSX_DEPLOYMENT_TARGET "14.0" CACHE STRING "Minimum native macOS target")\nendif()\nproject(HaloMacOSSourceAOT LANGUAGES C OBJC)')
    if 'option(BUILD_TESTING' not in cmake:
        cmake=cmake.replace('include(CTest)','option(BUILD_TESTING "Build host unit tests" OFF)\ninclude(CTest)')
    (ROOT/'overlay/port/macos/CMakeLists.txt').write_text(cmake)
    # Compare only audited translator modules, retaining complete pinned base prerequisites.
    runtime_patch=[]
    for rel in ('tools/recomp/config.py','tools/recomp/disasm.py','tools/recomp/lifter.py','tools/recomp/translator.py','templates/runtime/recomp_types.h'):
        original=subprocess.check_output(['git','show',pins['xboxrecomp']['commit']+':'+rel],cwd=runtime).decode()
        effective=(src/'tools/dependencies/xboxrecomp-runtime-overlay'/rel).read_text()
        runtime_patch.extend(difflib.unified_diff(original.splitlines(keepends=True),effective.splitlines(keepends=True),fromfile='a/'+rel,tofile='b/'+rel))
    (ROOT/'patches/xboxrecomp-runtime.patch').write_text(''.join(runtime_patch))
    files={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'overlay').rglob('*')) if f.is_file() and '__pycache__' not in f.parts}
    (ROOT/'overlay-manifest.json').write_text(json.dumps({'format':1,'scope':'Original macOS overlay plus separately licensed compiler-rt and project branding; fetched source and generated game translation are excluded','files_sha256':files},indent=2)+'\n')
    print('Refreshed focused source/runtime patches and overlay; review and fresh-build before publication.')

if __name__=='__main__':main()
