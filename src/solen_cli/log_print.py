from colorama import Fore


class LogPrint:
    """
    This class handles log writing and formating
    """

    @staticmethod
    def red(msg):
        return Fore.RED + msg + Fore.RESET

    @staticmethod
    def yellow(msg):
        return Fore.YELLOW + msg + Fore.RESET

    @staticmethod
    def green(msg):
        return Fore.GREEN + msg + Fore.RESET

    @staticmethod
    def blue(msg):
        return Fore.BLUE + msg + Fore.RESET

    def error(self, msg, should_exit=False):
        print(self.red(msg))
        if should_exit:
            raise SystemExit

    @staticmethod
    def info(msg):
        print(msg)

    def warning(self, msg):
        print(self.yellow(msg))

    def header(self, header):
        header = self.yellow(header)
        header_length = 40
        header_padding = "-"
        print(f"{header:{header_padding}^{header_length}}")
