class Sign:

    # Random initial ID for signs
    sign_id = 8000

    def __init__(self, vim, buffer, lineno):
        self.vim = vim
        self.id = self.get_id()
        self.buffer = buffer
        self.lineno = lineno
        self.placed = False

    @classmethod
    def get_id(cls):
        id = cls.sign_id
        cls.sign_id += 1
        return id

    def state(self, state):
        if self.placed:
            self.unplace()
        name = 'pytest_%s' % state
        self.vim.command('sign place %d line=%d name=%s buffer=%s' %
                         (self.id, self.lineno + 1, name, self.buffer))
        self.placed = True

    def unplace(self):
        self.vim.command('sign unplace %d' % self.id)
        self.placed = False


class Signs:

    def __init__(self, vim):
        self.vim = vim
        self.signs = {}

    def add(self, id, lineno):
        buffer = self.vim.current.buffer.number
        sign = Sign(self.vim, buffer, lineno)
        self.signs[id] = sign
        return sign

    def get(self, id):
        return self.signs[id]

    def remove_all(self):
        for key, sign in list(self.signs.items()):
            sign.unplace()
            del self.signs[key]
