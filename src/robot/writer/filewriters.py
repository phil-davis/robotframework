#  Copyright 2008-2015 Nokia Networks
#  Copyright 2016-     Robot Framework Foundation
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import ast

from robot.parsing.lexer import Token

from .formatters import TxtFormatter, PipeFormatter


def FileWriter(context):
    """Creates and returns a ``FileWriter`` object.

    :param context: The type of the returned ``FileWriter`` is determined based
        on ``context.format``. ``context`` is also passed to created writer.
    :type context: :class:`~robot.writer.datafilewriter.WritingContext`
    """
    if context.pipe_separated:
        return PipeSeparatedTxtWriter(context)
    return SpaceSeparatedTxtWriter(context)


class ColumnAligner(ast.NodeVisitor):

    def __init__(self, widths):
        self.widths = widths

    def visit_Statement(self, statement):
        if statement.type in (Token.TESTCASE_HEADER, Token.NAME):
            return
        for line in statement.lines:
            line_pos = 0
            exp_pos = 0
            for token, width in zip(line, self.widths):
                exp_pos += width
                token.value = (exp_pos - line_pos) * ' ' + token.value
                line_pos += len(token.value)


class Aligner(ast.NodeVisitor):
    _test_or_keyword_name_width = 18
    _setting_and_variable_name_width = 14

    def visit_Section(self, section):
        if section.type in (Token.SETTING_HEADER, Token.VARIABLE_HEADER):
            self.generic_visit(section)
        elif section.type == Token.TESTCASE_HEADER:
            if len(section.header) > 1:
                widths = [len(t.value) for t in section.header]
                ColumnAligner(widths[:-1]).visit(section)

    def visit_Statement(self, statement):
        for line in statement.lines:
            line[0].value = line[0].value.ljust(self._setting_and_variable_name_width)


class SeparatorRemover(ast.NodeVisitor):
    # TODO: remove empty rows

    def visit_Statement(self, statement):
        if statement.type == Token.TESTCASE_HEADER:
            self._add_whitespace_to_header_values(statement)
        statement.tokens = [t for t in statement.tokens
                            if t.type not in (Token.EOL, Token.SEPARATOR,
                                              Token.OLD_FOR_INDENT)]

    def _add_whitespace_to_header_values(self, statement):
        prev = None
        for token in statement.tokens:
            if token.type == Token.SEPARATOR and prev:
                prev.value += token.value[:-4] # TODO pipes??
            elif token.type == Token.TESTCASE_HEADER:
                prev = token
            else:
                prev = None


class ForLoopCleaner(ast.NodeVisitor):

    def visit_ForLoop(self, forloop):
        forloop.header[0].value = 'FOR'
        forloop.end[0].value = 'END'


class Writer(ast.NodeVisitor):

    def __init__(self, configuration):
        self.configuration = configuration
        self.output = configuration.output
        self.indent = 0
        self.pipes = configuration.pipe_separated
        self.separator = ' ' * configuration.txt_separating_spaces if not self.pipes else ' | '
        self.indent_marker = self.separator if not self.pipes else '   | '
        self._section_seen = False
        self._test_or_kw_seen = False
        self._test_case_section_headers = False

    def visit_Statement(self, statement):
        self._write_statement(statement)

    def visit_Section(self, section):
        if self._section_seen:
            self.output.write('\n')
        if section.type == Token.TESTCASE_HEADER:
            self._test_case_section_headers = len(section.header) > 1
        self.generic_visit(section)
        self._section_seen = True
        self._test_or_kw_seen = False
        self._test_case_section_headers = False

    def visit_TestOrKeyword(self, node):
        if self._test_or_kw_seen:
            self.output.write('\n')
        self._write_statement(node.name)
        self.indent += 1
        self.generic_visit(node.body)
        self.indent -= 1
        self._test_or_kw_seen = True

    def visit_ForLoop(self, node):
        self._write_statement(node.header)
        self.indent += 1
        self.generic_visit(node.body)
        self.indent -= 1
        self._write_statement(node.end)

    def _write_statement(self, statement):
        indent = self.indent * self.indent_marker
        for line in statement.lines:
            values = [t.value for t in line]
            row = indent + self.separator.join(values)
            if self.pipes:
                row = '| ' + row + ' |'
            else:
                row = row.rstrip()
            self.output.write(row)
            self.output.write('\n')


class _DataFileWriter(object):

    def __init__(self, configuration):
        self.config = configuration
        self._output = configuration.output

    def write(self, model):
        SeparatorRemover().visit(model)
        ForLoopCleaner().visit(model)
        Aligner().visit(model)
        Writer(self.config).visit(model)

    def _write_rows(self, rows):
        for row in rows:
            self._write_row(row)

    def _write_empty_row(self, table):
        self._write_row(self._formatter.empty_row_after(table))

    def _write_row(self, row):
        raise NotImplementedError

    def _write_section(self, section, is_last):
        self._write_rows(self._formatter.format_section(section))
        if not is_last:
            self._write_empty_row(section)


class SpaceSeparatedTxtWriter(_DataFileWriter):

    def __init__(self, configuration):
        self._separator = ' ' * configuration.txt_separating_spaces
        _DataFileWriter.__init__(self, configuration)

    def _write_row(self, row):
        line = self._separator.join(t.value for t in row).rstrip() + '\n'
        self._output.write(line)


class PipeSeparatedTxtWriter(_DataFileWriter):
    _separator = ' | '

    def __init__(self, configuration):
        _DataFileWriter.__init__(self, configuration)

    def _write_row(self, row):
        row = self._separator.join(t.value for t in row)
        if row:
            row = '| ' + row + ' |'
        self._output.write(row + '\n')
