import os
import sys

class Parser:
    def __init__(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            raw_lines = f.readlines()
        self.commands = []
        for line in raw_lines:
            clean = line.split('//')[0].strip()
            if clean:
                self.commands.append(clean)
        self.current_idx = -1
        self.current_cmd = ""

    def has_more_commands(self):
        return self.current_idx + 1 < len(self.commands)

    def advance(self):
        self.current_idx += 1
        self.current_cmd = self.commands[self.current_idx]

    def command_type(self):
        parts = self.current_cmd.split()
        cmd = parts[0]
        if cmd in ('add', 'sub', 'neg', 'eq', 'gt', 'lt', 'and', 'or', 'not'):
            return 'C_ARITHMETIC'
        elif cmd == 'push':
            return 'C_PUSH'
        elif cmd == 'pop':
            return 'C_POP'
        elif cmd == 'label':
            return 'C_LABEL'
        elif cmd == 'goto':
            return 'C_GOTO'
        elif cmd == 'if-goto':
            return 'C_IF'
        elif cmd == 'function':
            return 'C_FUNCTION'
        elif cmd == 'return':
            return 'C_RETURN'
        elif cmd == 'call':
            return 'C_CALL'
        raise ValueError(f"Unknown command: {cmd}")

    def arg1(self):
        ctype = self.command_type()
        parts = self.current_cmd.split()
        if ctype == 'C_ARITHMETIC':
            return parts[0]
        return parts[1]

    def arg2(self):
        parts = self.current_cmd.split()
        return int(parts[2])


class CodeWriter:
    def __init__(self, output_path):
        self.out = open(output_path, 'w', encoding='utf-8')
        self.filename = ""
        self.function_name = ""
        self.label_counter = 0

    def set_file_name(self, filename):
        self.filename = os.path.splitext(os.path.basename(filename))[0]

    def _write(self, lines):
        self.out.write('\n'.join(lines) + '\n')

    def write_init(self):
        self._write([
            '@256',
            'D=A',
            '@SP',
            'M=D'
        ])
        self.write_call('Sys.init', 0)

    def write_arithmetic(self, command):
        if command in ('add', 'sub', 'and', 'or'):
            op_map = {'add': 'M=M+D', 'sub': 'M=M-D', 'and': 'M=M&D', 'or': 'M=M|D'}
            self._write([
                '@SP',
                'AM=M-1',
                'D=M',
                'A=A-1',
                op_map[command]
            ])
        elif command in ('neg', 'not'):
            op_map = {'neg': 'M=-M', 'not': 'M=!M'}
            self._write([
                '@SP',
                'A=M-1',
                op_map[command]
            ])
        elif command in ('eq', 'gt', 'lt'):
            jump_map = {'eq': 'JEQ', 'gt': 'JGT', 'lt': 'JLT'}
            lbl_true = f"TRUE_{self.label_counter}"
            lbl_end = f"END_{self.label_counter}"
            self.label_counter += 1
            self._write([
                '@SP',
                'AM=M-1',
                'D=M',
                'A=A-1',
                'D=M-D',
                f'@{lbl_true}',
                f'D;{jump_map[command]}',
                '@SP',
                'A=M-1',
                'M=0',
                f'@{lbl_end}',
                '0;JMP',
                f'({lbl_true})',
                '@SP',
                'A=M-1',
                'M=-1',
                f'({lbl_end})'
            ])

    def write_push_pop(self, command, segment, index):
        seg_map = {'local': 'LCL', 'argument': 'ARG', 'this': 'THIS', 'that': 'THAT'}
        if command == 'C_PUSH':
            if segment == 'constant':
                self._write([
                    f'@{index}',
                    'D=A',
                    '@SP',
                    'A=M',
                    'M=D',
                    '@SP',
                    'M=M+1'
                ])
            elif segment in seg_map:
                self._write([
                    f'@{seg_map[segment]}',
                    'D=M',
                    f'@{index}',
                    'A=D+A',
                    'D=M',
                    '@SP',
                    'A=M',
                    'M=D',
                    '@SP',
                    'M=M+1'
                ])
            elif segment == 'temp':
                self._write([
                    f'@{5 + index}',
                    'D=M',
                    '@SP',
                    'A=M',
                    'M=D',
                    '@SP',
                    'M=M+1'
                ])
            elif segment == 'pointer':
                ptr = 'THIS' if index == 0 else 'THAT'
                self._write([
                    f'@{ptr}',
                    'D=M',
                    '@SP',
                    'A=M',
                    'M=D',
                    '@SP',
                    'M=M+1'
                ])
            elif segment == 'static':
                self._write([
                    f'@{self.filename}.{index}',
                    'D=M',
                    '@SP',
                    'A=M',
                    'M=D',
                    '@SP',
                    'M=M+1'
                ])
        elif command == 'C_POP':
            if segment in seg_map:
                self._write([
                    f'@{seg_map[segment]}',
                    'D=M',
                    f'@{index}',
                    'D=D+A',
                    '@R13',
                    'M=D',
                    '@SP',
                    'AM=M-1',
                    'D=M',
                    '@R13',
                    'A=M',
                    'M=D'
                ])
            elif segment == 'temp':
                self._write([
                    '@SP',
                    'AM=M-1',
                    'D=M',
                    f'@{5 + index}',
                    'M=D'
                ])
            elif segment == 'pointer':
                ptr = 'THIS' if index == 0 else 'THAT'
                self._write([
                    '@SP',
                    'AM=M-1',
                    'D=M',
                    f'@{ptr}',
                    'M=D'
                ])
            elif segment == 'static':
                self._write([
                    '@SP',
                    'AM=M-1',
                    'D=M',
                    f'@{self.filename}.{index}',
                    'M=D'
                ])

    def _get_scoped_label(self, label):
        if self.function_name:
            return f"{self.function_name}${label}"
        return label

    def write_label(self, label):
        scoped = self._get_scoped_label(label)
        self._write([f'({scoped})'])

    def write_goto(self, label):
        scoped = self._get_scoped_label(label)
        self._write([
            f'@{scoped}',
            '0;JMP'
        ])

    def write_if(self, label):
        scoped = self._get_scoped_label(label)
        self._write([
            '@SP',
            'AM=M-1',
            'D=M',
            f'@{scoped}',
            'D;JNE'
        ])

    def write_function(self, function_name, num_vars):
        self.function_name = function_name
        self._write([f'({function_name})'])
        for _ in range(num_vars):
            self.write_push_pop('C_PUSH', 'constant', 0)

    def write_call(self, function_name, num_args):
        ret_label = f"{function_name}$ret.{self.label_counter}"
        self.label_counter += 1
        self._write([
            f'@{ret_label}',
            'D=A',
            '@SP',
            'A=M',
            'M=D',
            '@SP',
            'M=M+1'
        ])
        for reg in ('LCL', 'ARG', 'THIS', 'THAT'):
            self._write([
                f'@{reg}',
                'D=M',
                '@SP',
                'A=M',
                'M=D',
                '@SP',
                'M=M+1'
            ])
        self._write([
            '@SP',
            'D=M',
            '@5',
            'D=D-A',
            f'@{num_args}',
            'D=D-A',
            '@ARG',
            'M=D',
            '@SP',
            'D=M',
            '@LCL',
            'M=D',
            f'@{function_name}',
            '0;JMP',
            f'({ret_label})'
        ])

    def write_return(self):
        self._write([
            '@LCL',
            'D=M',
            '@R13',
            'M=D',
            '@5',
            'A=D-A',
            'D=M',
            '@R14',
            'M=D',
            '@SP',
            'AM=M-1',
            'D=M',
            '@ARG',
            'A=M',
            'M=D',
            '@ARG',
            'D=M+1',
            '@SP',
            'M=D',
            '@R13',
            'AM=M-1',
            'D=M',
            '@THAT',
            'M=D',
            '@R13',
            'AM=M-1',
            'D=M',
            '@THIS',
            'M=D',
            '@R13',
            'AM=M-1',
            'D=M',
            '@ARG',
            'M=D',
            '@R13',
            'AM=M-1',
            'D=M',
            '@LCL',
            'M=D',
            '@R14',
            'A=M',
            '0;JMP'
        ])

    def close(self):
        self.out.close()


def translate_file(parser, writer):
    while parser.has_more_commands():
        parser.advance()
        ctype = parser.command_type()
        if ctype == 'C_ARITHMETIC':
            writer.write_arithmetic(parser.arg1())
        elif ctype in ('C_PUSH', 'C_POP'):
            writer.write_push_pop(ctype, parser.arg1(), parser.arg2())
        elif ctype == 'C_LABEL':
            writer.write_label(parser.arg1())
        elif ctype == 'C_GOTO':
            writer.write_goto(parser.arg1())
        elif ctype == 'C_IF':
            writer.write_if(parser.arg1())
        elif ctype == 'C_FUNCTION':
            writer.write_function(parser.arg1(), parser.arg2())
        elif ctype == 'C_CALL':
            writer.write_call(parser.arg1(), parser.arg2())
        elif ctype == 'C_RETURN':
            writer.write_return()


def main():
    if len(sys.argv) != 2:
        sys.exit(1)

    target = sys.argv[1]
    if os.path.isdir(target):
        norm_path = os.path.normpath(target)
        dir_name = os.path.basename(norm_path)
        out_path = os.path.join(norm_path, f"{dir_name}.asm")
        vm_files = [
            os.path.join(norm_path, f)
            for f in os.listdir(norm_path)
            if f.endswith('.vm')
        ]
        writer = CodeWriter(out_path)
        if any(os.path.basename(f) == 'Sys.vm' for f in vm_files):
            writer.write_init()
        for vm_file in sorted(vm_files):
            writer.set_file_name(vm_file)
            parser = Parser(vm_file)
            translate_file(parser, writer)
        writer.close()
    elif os.path.isfile(target) and target.endswith('.vm'):
        out_path = os.path.splitext(target)[0] + '.asm'
        writer = CodeWriter(out_path)
        writer.set_file_name(target)
        parser = Parser(target)
        translate_file(parser, writer)
        writer.close()


if __name__ == '__main__':
    main()
