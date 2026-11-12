import sys
import os

class SymbolTable:
    def __init__(self):
        self.table = {
            "SP": 0, "LCL": 1, "ARG": 2, "THIS": 3, "THAT": 4,
            "SCREEN": 16384, "KBD": 24576
        }
        for i in range(16):
            self.table[f"R{i}"] = i

    def add_entry(self, symbol, address):
        self.table[symbol] = address

    def contains(self, symbol):
        return symbol in self.table

    def get_address(self, symbol):
        return self.table[symbol]


class Parser:
    A_COMMAND = 0
    C_COMMAND = 1
    L_COMMAND = 2

    def __init__(self, filepath):
        self.commands = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                clean = line.split('//')[0].strip()
                clean = ''.join(clean.split())
                if clean:
                    self.commands.append(clean)
        self.current_idx = -1
        self.current_cmd = None

    def has_more_commands(self):
        return self.current_idx + 1 < len(self.commands)

    def advance(self):
        self.current_idx += 1
        self.current_cmd = self.commands[self.current_idx]

    def reset(self):
        self.current_idx = -1
        self.current_cmd = None

    def command_type(self):
        if self.current_cmd.startswith('@'):
            return self.A_COMMAND
        elif self.current_cmd.startswith('(') and self.current_cmd.endswith(')'):
            return self.L_COMMAND
        return self.C_COMMAND

    def symbol(self):
        cmd_type = self.command_type()
        if cmd_type == self.A_COMMAND:
            return self.current_cmd[1:]
        elif cmd_type == self.L_COMMAND:
            return self.current_cmd[1:-1]
        return None

    def dest(self):
        if '=' in self.current_cmd:
            return self.current_cmd.split('=')[0]
        return ""

    def comp(self):
        cmd = self.current_cmd
        if '=' in cmd:
            cmd = cmd.split('=')[1]
        if ';' in cmd:
            cmd = cmd.split(';')[0]
        return cmd

    def jump(self):
        if ';' in self.current_cmd:
            return self.current_cmd.split(';')[1]
        return ""


class Code:
    DEST_MAP = {
        "": "000", "M": "001", "D": "010", "MD": "011",
        "A": "100", "AM": "101", "AD": "110", "AMD": "111"
    }

    COMP_MAP = {
        "0":   "0101010", "1":   "0111111", "-1":  "0111010",
        "D":   "0001100", "A":   "0110000", "!D":  "0001101",
        "!A":  "0110001", "-D":  "0001111", "-A":  "0110011",
        "D+1": "0011111", "A+1": "0110111", "D-1": "0001110",
        "A-1": "0110010", "D+A": "0000010", "D-A": "0010011",
        "A-D": "0000111", "D&A": "0000000", "D|A": "0010101",
        "M":   "1110000", "!M":  "1110001", "-M":  "1110011",
        "M+1": "1110111", "M-1": "1110010", "D+M": "1000010",
        "D-M": "1010011", "M-D": "1000111", "D&M": "1000000",
        "D|M": "1010101"
    }

    JUMP_MAP = {
        "": "000", "JGT": "001", "JEQ": "010", "JGE": "011",
        "JLT": "100", "JNE": "101", "JLE": "110", "JMP": "111"
    }

    @staticmethod
    def dest(mnemonic):
        return Code.DEST_MAP[mnemonic]

    @staticmethod
    def comp(mnemonic):
        return Code.COMP_MAP[mnemonic]

    @staticmethod
    def jump(mnemonic):
        return Code.JUMP_MAP[mnemonic]


def assemble(asm_filepath):
    parser = Parser(asm_filepath)
    symbols = SymbolTable()

    rom_address = 0
    while parser.has_more_commands():
        parser.advance()
        cmd_type = parser.command_type()
        if cmd_type == Parser.L_COMMAND:
            symbols.add_entry(parser.symbol(), rom_address)
        else:
            rom_address += 1

    parser.reset()
    ram_address = 16
    output_lines = []

    while parser.has_more_commands():
        parser.advance()
        cmd_type = parser.command_type()
        if cmd_type == Parser.A_COMMAND:
            sym = parser.symbol()
            if sym.isdigit():
                address = int(sym)
            else:
                if not symbols.contains(sym):
                    symbols.add_entry(sym, ram_address)
                    ram_address += 1
                address = symbols.get_address(sym)
            output_lines.append(f"0{address:015b}")
        elif cmd_type == Parser.C_COMMAND:
            c_bits = Code.comp(parser.comp())
            d_bits = Code.dest(parser.dest())
            j_bits = Code.jump(parser.jump())
            output_lines.append(f"111{c_bits}{d_bits}{j_bits}")

    out_filepath = os.path.splitext(asm_filepath)[0] + ".hack"
    with open(out_filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines) + '\n')


if __name__ == '__main__':
    target_file = sys.argv[1] if len(sys.argv) == 2 else "Add.asm"
    assemble(target_file)
