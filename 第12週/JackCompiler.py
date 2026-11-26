import os
import re
import sys


class JackTokenizer:
    KEYWORDS = {
        'class', 'constructor', 'function', 'method', 'field', 'static',
        'var', 'int', 'char', 'boolean', 'void', 'true', 'false', 'null',
        'this', 'let', 'do', 'if', 'else', 'while', 'return'
    }
    SYMBOLS = {
        '{', '}', '(', ')', '[', ']', '.', ',', ';',
        '+', '-', '*', '/', '&', '|', '<', '>', '=', '~'
    }

    def __init__(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        code = self._remove_comments(code)
        self.tokens = self._tokenize(code)
        self.idx = -1
        self.current_token = None
        self.current_type = None

    def _remove_comments(self, text):
        pattern = re.compile(r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"', re.DOTALL | re.MULTILINE)
        def replacer(match):
            s = match.group(0)
            if s.startswith('/'):
                return ' '
            return s
        return re.sub(pattern, replacer, text)

    def _tokenize(self, text):
        token_spec = [
            ('STRING_CONST', r'"[^"\n]*"'),
            ('INT_CONST', r'\d+'),
            ('SYMBOL', r'[{}()\[\].,;+\-*/&|<>=~]'),
            ('IDENT_OR_KW', r'[A-Za-z_][A-Za-z0-9_]*'),
            ('SKIP', r'\s+'),
        ]
        tok_regex = '|'.join(f'(?P<{name}>{pattern})' for name, pattern in token_spec)
        tokens = []
        for mo in re.finditer(tok_regex, text):
            kind = mo.lastgroup
            val = mo.group()
            if kind == 'SKIP':
                continue
            elif kind == 'STRING_CONST':
                tokens.append(('STRING_CONST', val[1:-1]))
            elif kind == 'INT_CONST':
                tokens.append(('INT_CONST', int(val)))
            elif kind == 'SYMBOL':
                tokens.append(('SYMBOL', val))
            elif kind == 'IDENT_OR_KW':
                if val in self.KEYWORDS:
                    tokens.append(('KEYWORD', val))
                else:
                    tokens.append(('IDENTIFIER', val))
        return tokens

    def has_more_tokens(self):
        return self.idx + 1 < len(self.tokens)

    def advance(self):
        self.idx += 1
        self.current_type, self.current_token = self.tokens[self.idx]

    def peek(self):
        if self.idx + 1 < len(self.tokens):
            return self.tokens[self.idx + 1]
        return (None, None)

    def token_type(self):
        return self.current_type

    def key_word(self):
        return self.current_token

    def symbol(self):
        return self.current_token

    def identifier(self):
        return self.current_token

    def int_val(self):
        return self.current_token

    def string_val(self):
        return self.current_token


class SymbolTable:
    def __init__(self):
        self.class_scope = {}
        self.subroutine_scope = {}
        self.indices = {'STATIC': 0, 'FIELD': 0, 'ARG': 0, 'VAR': 0}

    def start_subroutine(self):
        self.subroutine_scope.clear()
        self.indices['ARG'] = 0
        self.indices['VAR'] = 0

    def define(self, name, sym_type, kind):
        idx = self.indices[kind]
        self.indices[kind] += 1
        if kind in ('STATIC', 'FIELD'):
            self.class_scope[name] = (sym_type, kind, idx)
        else:
            self.subroutine_scope[name] = (sym_type, kind, idx)

    def var_count(self, kind):
        return self.indices[kind]

    def kind_of(self, name):
        if name in self.subroutine_scope:
            return self.subroutine_scope[name][1]
        if name in self.class_scope:
            return self.class_scope[name][1]
        return None

    def type_of(self, name):
        if name in self.subroutine_scope:
            return self.subroutine_scope[name][0]
        if name in self.class_scope:
            return self.class_scope[name][0]
        return None

    def index_of(self, name):
        if name in self.subroutine_scope:
            return self.subroutine_scope[name][2]
        if name in self.class_scope:
            return self.class_scope[name][2]
        return None


class VMWriter:
    def __init__(self, output_path):
        self.out = open(output_path, 'w', encoding='utf-8')

    def write_push(self, segment, index):
        self.out.write(f"push {segment} {index}\n")

    def write_pop(self, segment, index):
        self.out.write(f"pop {segment} {index}\n")

    def write_arithmetic(self, command):
        self.out.write(f"{command}\n")

    def write_label(self, label):
        self.out.write(f"label {label}\n")

    def write_goto(self, label):
        self.out.write(f"goto {label}\n")

    def write_if(self, label):
        self.out.write(f"if-goto {label}\n")

    def write_call(self, name, n_args):
        self.out.write(f"call {name} {n_args}\n")

    def write_function(self, name, n_locals):
        self.out.write(f"function {name} {n_locals}\n")

    def write_return(self):
        self.out.write("return\n")

    def close(self):
        self.out.close()


class CompilationEngine:
    KIND_TO_SEG = {
        'STATIC': 'static',
        'FIELD': 'this',
        'ARG': 'argument',
        'VAR': 'local'
    }

    OP_MAP = {
        '+': 'add',
        '-': 'sub',
        '&': 'and',
        '|': 'or',
        '<': 'lt',
        '>': 'gt',
        '=': 'eq'
    }

    def __init__(self, tokenizer, vm_writer):
        self.tk = tokenizer
        self.vm = vm_writer
        self.st = SymbolTable()
        self.class_name = ""
        self.label_counter = 0
        if self.tk.has_more_tokens():
            self.tk.advance()

    def _eat(self, expected=None):
        val = self.tk.current_token
        if expected is not None and val != expected:
            raise SyntaxError(f"Expected '{expected}', got '{val}'")
        if self.tk.has_more_tokens():
            self.tk.advance()
        return val

    def _new_label(self, prefix):
        lbl = f"{self.class_name}_{prefix}_{self.label_counter}"
        self.label_counter += 1
        return lbl

    def compile_class(self):
        self._eat('class')
        self.class_name = self._eat()
        self._eat('{')
        while self.tk.token_type() == 'KEYWORD' and self.tk.key_word() in ('static', 'field'):
            self.compile_class_var_dec()
        while self.tk.token_type() == 'KEYWORD' and self.tk.key_word() in ('constructor', 'function', 'method'):
            self.compile_subroutine()
        self._eat('}')

    def compile_class_var_dec(self):
        kind = self._eat().upper()
        var_type = self._eat()
        name = self._eat()
        self.st.define(name, var_type, kind)
        while self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == ',':
            self._eat(',')
            name = self._eat()
            self.st.define(name, var_type, kind)
        self._eat(';')

    def compile_subroutine(self):
        self.st.start_subroutine()
        sub_type = self._eat()
        self._eat()
        sub_name = self._eat()
        if sub_type == 'method':
            self.st.define('this', self.class_name, 'ARG')
        self._eat('(')
        self.compile_parameter_list()
        self._eat(')')
        self.compile_subroutine_body(sub_type, sub_name)

    def compile_parameter_list(self):
        if self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == ')':
            return
        var_type = self._eat()
        name = self._eat()
        self.st.define(name, var_type, 'ARG')
        while self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == ',':
            self._eat(',')
            var_type = self._eat()
            name = self._eat()
            self.st.define(name, var_type, 'ARG')

    def compile_subroutine_body(self, sub_type, sub_name):
        self._eat('{')
        while self.tk.token_type() == 'KEYWORD' and self.tk.key_word() == 'var':
            self.compile_var_dec()
        n_locals = self.st.var_count('VAR')
        self.vm.write_function(f"{self.class_name}.{sub_name}", n_locals)
        if sub_type == 'constructor':
            n_fields = self.st.var_count('FIELD')
            self.vm.write_push('constant', n_fields)
            self.vm.write_call('Memory.alloc', 1)
            self.vm.write_pop('pointer', 0)
        elif sub_type == 'method':
            self.vm.write_push('argument', 0)
            self.vm.write_pop('pointer', 0)
        self.compile_statements()
        self._eat('}')

    def compile_var_dec(self):
        self._eat('var')
        var_type = self._eat()
        name = self._eat()
        self.st.define(name, var_type, 'VAR')
        while self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == ',':
            self._eat(',')
            name = self._eat()
            self.st.define(name, var_type, 'VAR')
        self._eat(';')

    def compile_statements(self):
        while self.tk.token_type() == 'KEYWORD' and self.tk.key_word() in ('let', 'if', 'while', 'do', 'return'):
            kw = self.tk.key_word()
            if kw == 'let':
                self.compile_let()
            elif kw == 'if':
                self.compile_if()
            elif kw == 'while':
                self.compile_while()
            elif kw == 'do':
                self.compile_do()
            elif kw == 'return':
                self.compile_return()

    def compile_let(self):
        self._eat('let')
        var_name = self._eat()
        is_array = False
        if self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == '[':
            is_array = True
            self._eat('[')
            self.compile_expression()
            self._eat(']')
            kind = self.st.kind_of(var_name)
            idx = self.st.index_of(var_name)
            self.vm.write_push(self.KIND_TO_SEG[kind], idx)
            self.vm.write_arithmetic('add')
        self._eat('=')
        self.compile_expression()
        self._eat(';')
        if is_array:
            self.vm.write_pop('temp', 0)
            self.vm.write_pop('pointer', 1)
            self.vm.write_push('temp', 0)
            self.vm.write_pop('that', 0)
        else:
            kind = self.st.kind_of(var_name)
            idx = self.st.index_of(var_name)
            self.vm.write_pop(self.KIND_TO_SEG[kind], idx)

    def compile_if(self):
        lbl_true = self._new_label('IF_TRUE')
        lbl_false = self._new_label('IF_FALSE')
        lbl_end = self._new_label('IF_END')
        self._eat('if')
        self._eat('(')
        self.compile_expression()
        self._eat(')')
        self.vm.write_if(lbl_true)
        self.vm.write_goto(lbl_false)
        self.vm.write_label(lbl_true)
        self._eat('{')
        self.compile_statements()
        self._eat('}')
        if self.tk.token_type() == 'KEYWORD' and self.tk.key_word() == 'else':
            self.vm.write_goto(lbl_end)
            self.vm.write_label(lbl_false)
            self._eat('else')
            self._eat('{')
            self.compile_statements()
            self._eat('}')
            self.vm.write_label(lbl_end)
        else:
            self.vm.write_label(lbl_false)

    def compile_while(self):
        lbl_exp = self._new_label('WHILE_EXP')
        lbl_end = self._new_label('WHILE_END')
        self.vm.write_label(lbl_exp)
        self._eat('while')
        self._eat('(')
        self.compile_expression()
        self._eat(')')
        self.vm.write_arithmetic('not')
        self.vm.write_if(lbl_end)
        self._eat('{')
        self.compile_statements()
        self._eat('}')
        self.vm.write_goto(lbl_exp)
        self.vm.write_label(lbl_end)

    def compile_do(self):
        self._eat('do')
        self._compile_subroutine_call()
        self._eat(';')
        self.vm.write_pop('temp', 0)

    def compile_return(self):
        self._eat('return')
        if self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == ';':
            self.vm.write_push('constant', 0)
        else:
            self.compile_expression()
        self._eat(';')
        self.vm.write_return()

    def compile_expression(self):
        self.compile_term()
        while self.tk.token_type() == 'SYMBOL' and self.tk.symbol() in ('+', '-', '*', '/', '&', '|', '<', '>', '='):
            op = self._eat()
            self.compile_term()
            if op in self.OP_MAP:
                self.vm.write_arithmetic(self.OP_MAP[op])
            elif op == '*':
                self.vm.write_call('Math.multiply', 2)
            elif op == '/':
                self.vm.write_call('Math.divide', 2)

    def compile_term(self):
        ttype = self.tk.token_type()
        if ttype == 'INT_CONST':
            val = self._eat()
            self.vm.write_push('constant', val)
        elif ttype == 'STRING_CONST':
            val = self._eat()
            self.vm.write_push('constant', len(val))
            self.vm.write_call('String.new', 1)
            for ch in val:
                self.vm.write_push('constant', ord(ch))
                self.vm.write_call('String.appendChar', 2)
        elif ttype == 'KEYWORD':
            kw = self._eat()
            if kw == 'true':
                self.vm.write_push('constant', 0)
                self.vm.write_arithmetic('not')
            elif kw in ('false', 'null'):
                self.vm.write_push('constant', 0)
            elif kw == 'this':
                self.vm.write_push('pointer', 0)
        elif ttype == 'SYMBOL' and self.tk.symbol() == '(':
            self._eat('(')
            self.compile_expression()
            self._eat(')')
        elif ttype == 'SYMBOL' and self.tk.symbol() in ('-', '~'):
            op = self._eat()
            self.compile_term()
            if op == '-':
                self.vm.write_arithmetic('neg')
            else:
                self.vm.write_arithmetic('not')
        elif ttype == 'IDENTIFIER':
            next_type, next_val = self.tk.peek()
            if next_type == 'SYMBOL' and next_val == '[':
                var_name = self._eat()
                self._eat('[')
                self.compile_expression()
                self._eat(']')
                kind = self.st.kind_of(var_name)
                idx = self.st.index_of(var_name)
                self.vm.write_push(self.KIND_TO_SEG[kind], idx)
                self.vm.write_arithmetic('add')
                self.vm.write_pop('pointer', 1)
                self.vm.write_push('that', 0)
            elif next_type == 'SYMBOL' and next_val in ('(', '.'):
                self._compile_subroutine_call()
            else:
                var_name = self._eat()
                kind = self.st.kind_of(var_name)
                idx = self.st.index_of(var_name)
                self.vm.write_push(self.KIND_TO_SEG[kind], idx)

    def _compile_subroutine_call(self):
        first_name = self._eat()
        n_args = 0
        if self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == '.':
            self._eat('.')
            sub_name = self._eat()
            kind = self.st.kind_of(first_name)
            if kind is not None:
                obj_type = self.st.type_of(first_name)
                idx = self.st.index_of(first_name)
                self.vm.write_push(self.KIND_TO_SEG[kind], idx)
                full_name = f"{obj_type}.{sub_name}"
                n_args = 1
            else:
                full_name = f"{first_name}.{sub_name}"
        else:
            self.vm.write_push('pointer', 0)
            full_name = f"{self.class_name}.{first_name}"
            n_args = 1
        self._eat('(')
        n_args += self.compile_expression_list()
        self._eat(')')
        self.vm.write_call(full_name, n_args)

    def compile_expression_list(self):
        count = 0
        if self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == ')':
            return count
        self.compile_expression()
        count += 1
        while self.tk.token_type() == 'SYMBOL' and self.tk.symbol() == ',':
            self._eat(',')
            self.compile_expression()
            count += 1
        return count


def compile_file(jack_path):
    vm_path = os.path.splitext(jack_path)[0] + '.vm'
    tokenizer = JackTokenizer(jack_path)
    writer = VMWriter(vm_path)
    engine = CompilationEngine(tokenizer, writer)
    engine.compile_class()
    writer.close()


def main():
    if len(sys.argv) != 2:
        sys.exit(1)

    target = sys.argv[1]
    if os.path.isdir(target):
        for fname in os.listdir(target):
            if fname.endswith('.jack'):
                compile_file(os.path.join(target, fname))
    elif os.path.isfile(target) and target.endswith('.jack'):
        compile_file(target)


if __name__ == '__main__':
    main()
