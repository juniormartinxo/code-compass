def helper(value: str) -> str:
    return value.strip()


class Service:
    KIND = "service"

    def load(self, value: str) -> str:
        return helper(value)

    def save(self, value: str) -> str:
        return self.load(value)
