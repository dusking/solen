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
    def log(repo, line=1):
        if repo:
            repo = Fore.GREEN + repo
            print("{0:<35}| {1}{2}".format(repo, line, Fore.RESET))
        else:
            print("{0}{1}".format(line, Fore.RESET))

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

    def log_multiline(self, repo, output):
        for line in output.split("\n"):
            if line:
                line = Fore.YELLOW + line
                self.log(repo, line)
