"""Recursive-descent parser: tokens in, AST out.

Grammar, from lowest to highest precedence:

    program    -> decl* EOF
    decl       -> "let" IDENT "=" expr ";" | "fn" IDENT function | stmt
    stmt       -> "if" expr block ("else" (if | block))?
                | "while" expr block | "return" expr? ";" | block | expr ";"
    expr       -> assignment
    assignment -> or ("=" assignment)?          (right associative)
    or         -> and ("or" and)*
    and        -> equality ("and" equality)*
    equality   -> comparison (("==" | "!=") comparison)*
    comparison -> term (("<" | "<=" | ">" | ">=") term)*
    term       -> factor (("+" | "-") factor)*
    factor     -> unary (("*" | "/" | "%") unary)*
    unary      -> ("-" | "not") unary | postfix
    postfix    -> primary ("(" args ")" | "[" expr "]")*
    primary    -> NUMBER | STRING | "true" | "false" | "nil" | IDENT
                | "(" expr ")" | "[" args "]" | "fn" function
"""

from __future__ import annotations

from kite import nodes as n
from kite.errors import KiteSyntaxError
from kite.lexer import Token, tokenize

LITERALS = {"true": True, "false": False, "nil": None}


def parse(source: str) -> n.Program:
    return _Parser(tokenize(source)).program()


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    # ---- helpers -----------------------------------------------------------

    def _peek(self, ahead: int = 0) -> Token:
        return self.tokens[min(self.pos + ahead, len(self.tokens) - 1)]

    def _check(self, *kinds: str) -> bool:
        return self._peek().kind in kinds

    def _advance(self) -> Token:
        token = self._peek()
        if token.kind != "EOF":
            self.pos += 1
        return token

    def _match(self, *kinds: str) -> Token | None:
        return self._advance() if self._check(*kinds) else None

    def _expect(self, kind: str, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        raise self._error(message)

    def _error(self, message: str, token: Token | None = None) -> KiteSyntaxError:
        token = token or self._peek()
        return KiteSyntaxError(message, token.line, token.col)

    # ---- declarations and statements --------------------------------------

    def program(self) -> n.Program:
        body = []
        while not self._check("EOF"):
            body.append(self._declaration())
        return n.Program(tuple(body))

    def _declaration(self) -> object:
        if self._check("let"):
            return self._let()
        if self._check("fn") and self._peek(1).kind == "IDENT":
            keyword = self._advance()
            name = self._advance()
            function = self._function(name.text, keyword.line)
            return n.FnDecl(name.text, function, keyword.line, name.col)
        return self._statement()

    def _let(self) -> n.Let:
        keyword = self._advance()
        name = self._expect("IDENT", "expected variable name")
        self._expect("=", f"expected '=' after '{name.text}'")
        value = self._expression()
        self._expect(";", "expected ';' after variable declaration")
        return n.Let(name.text, value, keyword.line, name.col)

    def _function(self, name: str | None, line: int) -> n.FunctionExpr:
        self._expect("(", "expected '(' before parameters")
        params: list[n.Variable] = []
        if not self._check(")"):
            while True:
                tok = self._expect("IDENT", "expected parameter name")
                if any(p.name == tok.text for p in params):
                    raise self._error(f"duplicate parameter '{tok.text}'", tok)
                params.append(n.Variable(tok.text, tok.line, tok.col))
                if not self._match(","):
                    break
        self._expect(")", "expected ')' after parameters")
        body = self._block().body
        return n.FunctionExpr(name, tuple(params), body, line)

    def _statement(self) -> object:
        if self._check("if"):
            return self._if()
        if self._check("while"):
            keyword = self._advance()
            condition = self._expression()
            return n.While(condition, self._block(), keyword.line)
        if self._check("return"):
            keyword = self._advance()
            value = None if self._check(";") else self._expression()
            self._expect(";", "expected ';' after return value")
            return n.Return(value, keyword.line, keyword.col)
        if self._check("{"):
            return self._block()
        expr = self._expression()
        self._expect(";", "expected ';' after expression")
        return n.ExprStmt(expr, expr.line)

    def _if(self) -> n.If:
        keyword = self._advance()
        condition = self._expression()
        then = self._block()
        otherwise = None
        if self._match("else"):
            otherwise = self._if() if self._check("if") else self._block()
        return n.If(condition, then, otherwise, keyword.line)

    def _block(self) -> n.Block:
        brace = self._expect("{", "expected '{'")
        body = []
        while not self._check("}", "EOF"):
            body.append(self._declaration())
        self._expect("}", "expected '}' to close the block")
        return n.Block(tuple(body), brace.line)

    # ---- expressions -------------------------------------------------------

    def _expression(self) -> object:
        return self._assignment()

    def _assignment(self) -> object:
        target = self._or()
        equals = self._match("=")
        if equals is None:
            return target
        value = self._assignment()
        if isinstance(target, n.Variable):
            return n.Assign(target.name, value, target.line, target.col)
        if isinstance(target, n.Index):
            return n.SetIndex(target.target, target.index, value, target.line)
        raise self._error("invalid assignment target", equals)

    def _or(self) -> object:
        expr = self._and()
        while op := self._match("or"):
            expr = n.Logical("or", expr, self._and(), op.line)
        return expr

    def _and(self) -> object:
        expr = self._binary_level(0)
        while op := self._match("and"):
            expr = n.Logical("and", expr, self._binary_level(0), op.line)
        return expr

    # Binary levels, from equality to factor. All are left associative.
    LEVELS = (("==", "!="), ("<", "<=", ">", ">="), ("+", "-"), ("*", "/", "%"))

    def _binary_level(self, level: int) -> object:
        if level == len(self.LEVELS):
            return self._unary()
        expr = self._binary_level(level + 1)
        while op := self._match(*self.LEVELS[level]):
            right = self._binary_level(level + 1)
            expr = n.Binary(op.kind, expr, right, op.line)
        return expr

    def _unary(self) -> object:
        if op := self._match("-", "not"):
            return n.Unary(op.kind, self._unary(), op.line)
        return self._postfix()

    def _postfix(self) -> object:
        expr = self._primary()
        while True:
            if paren := self._match("("):
                args = self._items(")")
                expr = n.Call(expr, args, paren.line)
            elif bracket := self._match("["):
                index = self._expression()
                self._expect("]", "expected ']' after index")
                expr = n.Index(expr, index, bracket.line)
            else:
                return expr

    def _items(self, closing: str) -> tuple:
        items = []
        if not self._check(closing):
            while True:
                items.append(self._expression())
                if not self._match(","):
                    break
        self._expect(closing, f"expected '{closing}'")
        return tuple(items)

    def _primary(self) -> object:
        tok = self._peek()
        if tok.kind in ("NUMBER", "STRING"):
            self._advance()
            return n.Literal(tok.value, tok.line)
        if tok.kind in LITERALS:
            self._advance()
            return n.Literal(LITERALS[tok.kind], tok.line)
        if tok.kind == "IDENT":
            self._advance()
            return n.Variable(tok.text, tok.line, tok.col)
        if tok.kind == "(":
            self._advance()
            expr = self._expression()
            self._expect(")", "expected ')' after expression")
            return expr
        if tok.kind == "[":
            self._advance()
            return n.ListLiteral(self._items("]"), tok.line)
        if tok.kind == "fn":
            self._advance()
            return self._function(None, tok.line)
        raise self._error("expected an expression")
