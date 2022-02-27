import os
import glob
import json
import time
import logging
from typing import Union
from pathlib import Path

import requests
from asyncit.dicts import DotDict
from arweave.arweave_lib import Wallet, Transaction
from arweave.transaction_uploader import get_uploader

logger = logging.getLogger(__name__)


class Arweave:
    """Arewave client

    :param wallet_key_pair: Path to your arweave key pair file.
    """

    def __init__(self, wallet_key_pair: str):
        self.config_folder = None
        self.wallet = Wallet(wallet_key_pair)

    def set_config_folder(self, config_folder: str):
        """Set path to a folder that the upload data will be saved.

        :param config_folder: Path to a folder.
        """
        if not os.path.isdir(config_folder):
            raise NotADirectoryError("config folder does not exists, please enter valid path")

        self.config_folder = Path(config_folder)

    def upload_data(self, data: Union[str, dict]) -> Union[str, None]:
        """Get data as string or dictionary and upload it return data's url.

        :param data: Can be string or dictionary.
        """
        data = data if isinstance(data, str) else json.dumps(data, indent=4)
        user_encode_data = data.encode("utf-8")
        tx = Transaction(self.wallet, data=user_encode_data)
        tx.add_tag("Content-Type", "application/json")
        tx.sign()
        tx.send()
        url = f"{tx.api_url}/{tx.id}/"
        return url if self.validate_upload(url) else False

    def upload_file(self, file_path: str, content_type=None) -> Union[str, None]:
        """Get path of the file to upload and return the url of the file's data in arweave.

        :param file_path: Path to the file to upload.
        :param content_type: The type of the file.
        """
        if not os.path.isfile(f"{file_path}"):
            raise FileNotFoundError

        if not content_type:
            file_extension = os.path.splitext(file_path)[1]
            file_extension = file_extension.split(".")[1]
            if file_extension == "png":
                content_type = f"image/{file_extension}"
            elif file_extension == "json":
                content_type = f"application/{file_extension}"
            else:
                raise Exception(f"Unknown content-type for {file_extension}, supported files: .png, .json")

        logger.info(f"going to upload: {file_path}")
        try:
            with open(file_path, "rb", buffering=0) as file_handler:
                tx = Transaction(self.wallet, file_handler=file_handler, file_path=file_path)
                tx.add_tag("Content-Type", content_type)
                tx.sign()
                uploader = get_uploader(tx, file_handler)
                while not uploader.is_complete:
                    uploader.upload_chunk()

            url = f"{tx.api_url}/{tx.id}/"
        except Exception as ex:
            logger.error(f"failed to upload file: {file_path}, ex: {ex}")
            return None

        return url if self.validate_upload(url) else False

    def upload_pair(self, json_file_path: str, png_file_path: str) -> Union[str, None]:
        """Get json file path and png file path,
        upload the png, update the json file with the returned url(from upload) and upload the json.

        :param json_file_path: Path to json file to upload.
        :param png_file_path: Path to png file to upload.
        """
        if not (os.path.isfile(json_file_path) and os.path.isfile(png_file_path)):
            raise FileNotFoundError

        upload_png_url = self.upload_file(png_file_path)
        if not upload_png_url:
            logger.error("failed to upload the png file")
            return None

        self.update_json_metadata(json_file_path, upload_png_url)
        json_upload_url = self.upload_file(json_file_path)
        if json_upload_url:
            logger.info(
                f"upload pair succeeded: json: {json_file_path} ,png: {png_file_path}, json url: {json_upload_url}"
            )
            return json_upload_url

        logger.error("failed to upload the json file")
        return None

    def upload_from_folder(self, folder_file_path: str):
        """Handle upload pairs of (json, png) from folder.

        The folder expects to contain json and png files with the same name.
        Names should be numbers from 0 and up, for example: 0.json, 0.png, 2.json, 1.png.

        :param folder_file_path: Path to a folder that should contain jsons and pngs.

        >>> ar = Arweave("path to your wallet key pair file")
        >>> ar.upload_from_folder("/some/folder/on/your/system")

        In case of upload failures you can run the function again - it'll upload only failed files.
        The function use an auto generated file to handle the upload and failures.
        The auto generated file will be created in the [self.config_folder]/[folder_name].json
        """
        if not os.path.isdir(folder_file_path):
            raise NotADirectoryError

        if not self.config_folder:
            raise ValueError("Missing config folder")

        folder_name = Path(folder_file_path).stem
        in_process_file = self.config_folder.joinpath(f"{folder_name}.json")
        if in_process_file.exists():
            uploads_data = json.loads(in_process_file.read_text(encoding="utf-8"))
        else:
            json_files = glob.glob(f"{folder_file_path}/*.json")
            png_files = glob.glob(f"{folder_file_path}/*.png")
            json_names = {i.split(".")[0] for i in json_files}
            png_names = {i.split(".")[0] for i in png_files}
            if len(json_names - png_names) > 0 or len(png_names - json_names) > 0:
                logger.error(f"folder {folder_file_path} contain invalid couples of json and png files")
                return

            pairs = []
            for json_file in json_files:
                if json_file.split(".")[0] + ".png" in png_files:
                    png_file = json_file.split(".")[0] + ".png"
                    pairs.append(tuple((json_file, png_file)))
            uploads_data = {}
            for index, pair in enumerate(pairs):
                pair_data = {"json_file": pair[0], "png_file": pair[1], "json_url": "", "success": False}
                uploads_data[index] = pair_data

        for index, pair_data in uploads_data.items():
            pair_data = DotDict(pair_data)
            if pair_data.success:
                continue

            json_url = self.upload_pair(pair_data.json_file, pair_data.png_file)
            if json_url:
                uploads_data[index]["json_url"] = json_url
                uploads_data[index]["success"] = True
                in_process_file.write_text(json.dumps(uploads_data), encoding="utf-8")

    def validate_upload(self, url: str) -> bool:
        """Check if upload succeeded.

        :param url: The url of the data in arweave.
        """
        timeout = 60
        response = None
        for i in range(timeout):
            response = requests.get(url)
            if response.status_code == 200:
                logger.info(f"upload succeeded: {url}")
                return True

            time.sleep(1)

        logger.error(f"couldn't find link with the data, response: {response}")
        return False

    def update_json_metadata(self, json_file_path: str, png_url: str):
        """Update the json with the new png's url that was uploaded to arweave.

        :param json_file_path: path to a json file.
        :param png_url: the url of the png file in arweave.

        The json expected to meet the Token Metadata Standard
        (https://docs.metaplex.com/token-metadata/Versions/v1.0.0/nft-standard).
         The "image" key and first index of the properties.files will be updated to hold the given arweave image as uri.
        """
        png_url = png_url.strip("/") + "?ext=png"
        with open(json_file_path, "r+", encoding="UTF-8") as f:
            data = json.load(f)
            data["image"] = png_url
            data["properties"]["files"][0]["uri"] = png_url
            f.seek(0)
            json.dump(data, f)
            f.truncate()

    def bulk_upload_json_files(self, folder_file_path: str):
        """Upload all json files in folder.

        :param folder_file_path: Path to folder (should contain json files).
        """
        if not os.path.isdir(folder_file_path):
            raise NotADirectoryError

        if not self.config_folder:
            raise ValueError("Missing config folder")

        uploads_data = {}
        folder_name = Path(folder_file_path).stem
        in_process_file = self.config_folder.joinpath(f"{folder_name}.json")
        json_files = glob.glob(f"{folder_file_path}/*.json")
        for json_file in json_files:
            url = self.upload_file(json_file)
            if url:
                file_name = Path(json_file).stem
                uploads_data[file_name] = url
                in_process_file.write_text(json.dumps(uploads_data), encoding="utf-8")
