from argparse import ArgumentParser, Namespace
from typing import Tuple, Iterator
import logging
import sys
import glob
import os
import commentjson
import zipfile
import gitfiles
import lark
import time
import json
import shutil

# Load .gitignore file
gitfiles.load_gitignore()

logging.basicConfig(
    format="[%(asctime)s] [%(name)s/%(levelname)s]: %(message)s",
    datefmt="%I:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    level=logging.INFO,
)
log = logging.getLogger("mcaddon")


def type_abbr(type: str) -> str:
    match type:
        case "behavior":
            return "BP"
        case "resource":
            return "RP"
        case "skin":
            return "SP"


def pack_type(type: str):
    match type:
        case "data":
            return "behavior"
        case "resources":
            return "resource"
        case "skin_pack":
            return "skin"


def find_packs(dir: str) -> Iterator[Tuple[str, dict[str, str]]]:
    """
    Find all packs in the given directory.

    :param dir: The directory to search for packs.
    :type dir: str
    :return: An iterator of tuples containing the pack directory and pack metadata.
    :rtype: Iterator[Tuple[str, dict[str, str]]]
    """
    root_dir = os.path.realpath(dir)
    for fn in glob.glob("**/manifest.json", root_dir=root_dir, recursive=True):
        if gitfiles.match(fn):
            continue
        fp = os.path.join(root_dir, fn)
        pack_dir = os.path.dirname(os.path.relpath(fp, root_dir))
        pack_metadata = {"uuid": None, "version": None, "type": None, "name": None}
        try:
            with open(fp) as fd:
                data = commentjson.load(fd)
                pack_metadata["uuid"] = data["header"]["uuid"]
                pack_metadata["name"] = data["header"]["name"]
                pack_metadata["version"] = ".".join(
                    [str(x) for x in data["header"]["version"]]
                )
                for module in data["modules"]:
                    if module["type"] in ["data", "resources", "skin_pack"]:
                        pack_metadata["type"] = pack_type(module["type"])

                pack_metadata["abbr"] = type_abbr(pack_metadata["type"])
        except commentjson.JSONLibraryException as err:
            log.warning("Failed to load %s: %s", pack_dir, err.message)
            continue
        except KeyError as err:
            log.warning("Failed to load %s: %s", pack_dir, err)
            continue
        log.info("Found pack: %s with metadata: %s", pack_dir, pack_metadata)
        yield pack_dir, pack_metadata


def artifact_name(args: Namespace, pack_dir: str, pack_metadata: dict[str, str]) -> str:
    """
    Generate the artifact name based on the given arguments, pack directory, and pack metadata.

    :param args: The command line arguments.
    :type args: Namespace
    :param pack_dir: The directory of the pack.
    :type pack_dir: str
    :param pack_metadata: The metadata of the pack.
    :type pack_metadata: dict[str, str]
    :return: The generated artifact name.
    :rtype: str
    """
    name = args.outputPattern
    data = {"dirname": os.path.basename(pack_dir)}
    data.update(pack_metadata)
    for k, v in data.items():
        name = name.replace(k.upper(), v)
    res = os.path.join(args.output, "libs", name)
    log.debug("\tGenerated artifact name: %s", res)
    return res


def compile_pack(args: Namespace, pack_dir: str, pack_metadata: dict[str, str]):
    """
    Compile the pack into a zip file.

    :param args: The command line arguments.
    :type args: Namespace
    :param pack_dir: The directory of the pack.
    :type pack_dir: str
    :param pack_metadata: The metadata of the pack.
    :type pack_metadata: dict[str, str]
    """
    start = time.time()
    fp = os.path.join(args.output, "tmp", pack_dir)
    zf = artifact_name(args, pack_dir, pack_metadata)
    with zipfile.ZipFile(zf, mode="w") as zip:
        log.debug("\tCreating zip file: %s", zf)
        content = {"content": []}
        for root, dirs, files in os.walk(fp):
            for f in files:
                file = os.path.join(root, f)
                # if gitfiles.match(file):
                #     continue
                with open(file, "rb") as fd:
                    data = fd.read()
                    if file.endswith((".json", ".jsonc", ".json5")):
                        try:
                            temp = commentjson.loads(data)
                            data = commentjson.dumps(temp)
                        except (
                            commentjson.JSONLibraryException,
                            ValueError,
                            lark.exceptions.UnexpectedToken,
                        ):
                            ...
                    name = os.path.relpath(file, fp)
                    content["content"].append({"path": name.replace("\\", "/")})
                    log.debug("\tAdding file to zip: %s", name)
                    zip.writestr(name, data)

        # Make contents.json
        log.debug("\tWriting contents.json to zip")
        zip.writestr("contents.json", commentjson.dumps(content))

    log.info("\033[92mDone in %s ms\033[0m", round(time.time() - start, 2))


def build_script(fp: str, output: str):
    """
    Execute the build script.

    :param fp: The file path of the build script.
    :type fp: str
    """
    log.info("Executing build script: %s", fp)
    with open(fp) as fd:
        wdir = os.getcwd()
        script = (
            f"import os; os.chdir({ repr(os.path.join(output, 'tmp')) })\n{ fd.read() }"
        )
        exec_globals = {"log": logging.getLogger(os.path.basename(fp))}
        exec(script, exec_globals)
        if "build" in exec_globals:
            exec_globals["build"]()
        else:
            log.warning("No 'build' function found in the build script")
        os.chdir(wdir)


def copy_tree(src, dst) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=lambda dir, contents: [
            f for f in contents if gitfiles.match(os.path.join(dir, f))
        ],
    )


def main():
    """
    Main function to execute the build process.
    """
    outputs = {}
    # Exclude files in artifact
    excluded = ["*.py", "*.bat", "__pycache__/*", "contents.json"]  # Generated
    for p in excluded:
        gitfiles.__ignore_filter__.patterns.add(p)

    parser = ArgumentParser()
    parser.add_argument("-s", "--buildScript", type=str, nargs="?")
    parser.add_argument("-i", "--input", type=str, default=".")
    parser.add_argument("-o", "--output", type=str, default="build")
    parser.add_argument(
        "-p", "--outputPattern", type=str, default="DIRNAME-VERSION.mcpack"
    )
    parser.add_argument("-d", "--debug", action="store_true")

    args, unknown = parser.parse_known_args()
    TMP = os.path.join(args.output, "tmp")
    log.info("Running with args: %s", args)

    # Change log level
    if args.debug:
        log.setLevel(logging.DEBUG)

    log.info("Creating artifact directory: %s", args.output)
    if os.path.exists(args.output):
        shutil.rmtree(args.output)
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(os.path.join(args.output, "libs"), exist_ok=True)

    # Copy source over to build/tmp
    copy_tree(args.input, TMP)

    # Execute build script
    if args.buildScript != "none" and args.buildScript:
        start = time.time()
        sys.argv = unknown
        sys.argv.insert(0, args.buildScript)
        build_script(args.buildScript, args.output)
        log.info("\033[92mFinished in %s ms\033[0m", round(time.time() - start, 2))

    # Find all packs
    packs = list(find_packs(TMP))
    for pack in packs:
        log.info("Bundling pack: %s", pack[0])
        compile_pack(args, *pack)
    if len(packs) == 0:
        log.warning("\033[91mNo packs found: %s!\033[0m", TMP)

    # Add pack metadata to outputs
    outputs["packs"] = [pack[1] for pack in packs]

    # Output pack metadata to GitHub outputs
    if os.getenv("GITHUB_OUTPUT"):
        log.debug("Writing pack metadata to GitHub outputs")
        with open(os.getenv("GITHUB_OUTPUT"), "a") as fh:
            for k, v in outputs.items():
                fh.write(f"{ k }={ json.dumps(v) }\n")


if __name__ == "__main__":
    log.info("Starting build process")
    main()
    log.info("\033[92mBuild process finished\033[0m")
