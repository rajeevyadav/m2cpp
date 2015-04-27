import string
import re
import collection as col

letters = string.letters
digits = string.digits

expression_start = letters + digits + "[(~-+:"
expression_end = "%])},;\n"

list_start = "[({"
list_end = "]})"

prefixes = "-+~"
postfix1 = "'"
postfix2 = ".'"
operator1 = r"^\/*+:<>&|"
operator2 = (
    ".^", ".\\", "./", ".*",
    "<=", ">=", "==", "~=",
    "&&", "||")

def process(text, disp=True):
    """Process raw Matlab-code and create a token tree
representation of the code.

Parameters
----------
text : str
    String of Matlab code. Unformated.
disp : bool
    Print progress to screen if True.

Returns
-------
tree : Node
    Token-tree representation of code
    """

    # Preamble

    A = text+"\n\n\n"   # Padding to avoid eol-read-errors

    def create_program():
        """Create program

Returns
-------
tree : Node
    Node representation of tree
        """

        if disp:
            print "%4d %4d Program" % (0, 0)

        # Create intial nodes
        program = col.Program()
        program.line = 0
        program.cur = 0

        program.code = A

        includes = col.Includes(program)

        inc1 = col.Include(includes, "armadillo")
        inc1.value = "#include <armadillo>"
        inc1.code = ""

        inc2 = col.Include(includes, "usingarma")
        inc2.value = "using namespace arma ;"
        inc2.code = ""

        # Start processing

        mainblock = None
        line = 0
        cur = 0

        while True:

            if A[cur] == "\n":

                line += 1

            elif A[cur] in " \t;":
                continue

            elif A[cur] == "%":
                cur = findend_comment(cur)

            elif A[cur:cur+8] == "function":
                cur, line = create_function(program, cur, line)

            else:

                if mainblock is None:

                    if disp:
                        print "%4d %4d Function (main)" %\
                            (cur, line)

                    mainblock = create_main(program, cur, line)

                cur, line = fill_codeblock(mainblock, cur, line)

            if len(A)-cur<=2:
                break
            cur += 1

        return program


    def create_main(program, cur, line):
        "Create main function"

        func = col.Func(program, "main")
        func.cur = cur
        func.line = line

        declares = col.Declares(func)
        returns = col.Returns(func)
        params = col.Params(func)

        func["backend"] = "func_return"
        declares["backend"] = "func_return"
        returns["backend"] = "func_return"
        params["backend"] = "func_return"

        var = col.Var(returns, "_retval")
        var.type = "int"
        var.declare()

        argc = col.Var(params, "argc")
        argc.type = "int"

        argv = col.Var(params, "argv")
        argv.type = "char"
        argv["backend"] = "char"
        argv.pointer(2)

        block = col.Block(func)
        block.cur = cur
        block.line = line

        return block


    def create_function(program, cur, line):

        assert A[cur:cur+8] == "function"
        assert A[cur+8] in " ("

        start = cur

        if disp:
            print "%4d %4d Function" % (cur, line),
            print repr(A[start:A.find("\n", cur)+1])


        cur = cur + 8

        eol = A.find("\n", cur) # end of line

        # Return values
        loc_eq = A.find("=", cur, eol)
        if loc_eq != -1:
            rs = re.findall(r"[_\w\d]+", A[cur:loc_eq])

        else:
            rs = []

        # Parameters and name
        lpar = A.find("(", loc_eq+1, eol)
        if lpar != -1:
            rpar = A.find(")")
            param_names = re.findall(r"@?[_\w\d]+", A[lpar+1:rpar])
            name = A[loc_eq+1:lpar].strip()

        else:
            param_names = []
            name = A[loc_eq+1:eol]

        # Construct

        func = col.Func(program, name)
        func.cur = cur
        func.line = line
        col.Declares(func)

        returns = col.Returns(func)
        for r in rs:
            col.Var(returns, r)

        params = col.Params(func)
        for name in param_names:
            col.Var(params, name)

        block = col.Block(func)
        block.line = line+1
        block.cur = eol+1
        cur, line = fill_codeblock(block, cur, line)

        # Postfix
        if len(rs) == 1:
            func["backend"] = "func_return"
            func[0]["backend"] = "func_return"
            func[1]["backend"] = "func_return"
            func[2]["backend"] = "func_return"
        else:
            func["backend"] = "func_returns"
            func[0]["backend"] = "func_returns"
            func[1]["backend"] = "func_returns"
            func[2]["backend"] = "func_returns"

        for var in returns:
            var.declare()

        end = cur
        func.code = A[start:end+1]

        return cur, line


    def fill_codeblock(block, cur, line):

        assert block.parent["class"] != "Block"

        if disp:
            print "%4d %4d Codeblock" % (cur, line)

        while True:

            if A[cur] in " \t;":
                pass

            elif A[cur] == "\n":
                line += 1
                if len(A)-cur < 3:
                    return cur, line

            elif A[cur] == "%":

                cur, line = create_comment(block, cur, line)

            elif A[cur] == "[":

                # Divide beween statement and assignment
                eq_loc = findend_matrix(cur)

                while A[eq_loc] in " \t":
                    eq_loc += 1

                if A[eq_loc] == "=" and A[eq_loc+1] != "=":

                    cur, line = create_assigns(block, cur, line, eq_loc)

                else:

                    statement = col.Statement(block)
                    statement.cur = cur
                    statement.line = line

                    end = findend_expression(cur)
                    if disp:
                        print "%4d %4d   Statement" % (cur, line),
                        print A[cur:end+1]

                    statement.code = A[cur:end+1]

                    cur, line = create_expression(
                            statement, cur, line, end=end)


            elif A[cur] == "'":

                end = findend_string(cur)
                if disp:
                    print "%4d %4d   Statement" % (cur, line),
                    print A[cur:end+1]

                statement = col.Statement(block)
                statement.cur = cur
                statement.line = line
                statement.code = A[cur:end+1]

                cur, line = create_string(statement, cur, line)

            elif A[cur:cur+3] == "for" and A[cur+3] in " (":

                cur, line = create_for(block, cur, line)

            elif A[cur:cur+5] == "while" and A[cur+5] in " (":

                cur, line = create_while(block, cur, line)

            elif A[cur:cur+6] == "switch" and A[cur+6] in " (":
                cur, line = create_switch(block, cur, line)

            elif A[cur:cur+3] == "try" and A[cur+3] in " (\n":
                cur, line = create_try(block, cur+3, line)

            elif A[cur:cur+3] == "end" and A[cur+3] in " ;\n":
                return cur+3, line

            elif A[cur:cur+8] == "function" and A[cur+8] in " (":
                return cur-1, line

            elif A[cur] in expression_start:
                j = findend_expression(cur)
                while A[j] == " ":
                    j += 1
                eq_loc = j

                if A[eq_loc] == "=" and A[eq_loc+1] != "=":

                    cur, line = create_assign(block, cur, line, eq_loc)

                else:
                    end = findend_expression(cur)
                    if disp:
                        print "%4d %4d   Statement" % (cur, line),
                        print repr(A[cur:end])

                    statement = col.Statement(block)
                    statement.cur = cur
                    statement.line = line
                    statement.code = A[cur:end]

                    cur, line = create_expression(statement,
                            cur, line, end=end)

            cur += 1

            if len(A)-cur<3:
                return cur, line


    def create_assigns(parent, cur, line, eq_loc):

        assert A[cur] == "["
        assert A[eq_loc] == "="

        j = eq_loc+1
        while A[j] in " \t":
            j += 1
        end = findend_expression(j)

        if disp:
            print "%4d %4d   Assigns      " %\
                    (cur, line),
            print repr(A[cur:end])

        l = iterate_list(cur)

        if len(l[0]) == 1:
            return create_assign(parent, cur, line, eq_loc)

        assigns = col.Assigns(parent)
        assigns.cur = cur
        assigns.line = line
        assigns.code = A[cur:end]

        for vector in l:
            for start,stop in vector:
                create_assign_variable(assigns, start, line, end=stop)

        cur = eq_loc + 1
        while A[cur] in " \t":
            cur += 1

        cur_, line =  create_expression(assigns, cur, line)

        return cur_, line


    def create_assign(parent, cur, line, eq_loc):

        assert A[cur] in letters
        assert A[eq_loc] == "="

        j = eq_loc+1
        while A[j] in " \t":
            j += 1
        end = findend_expression(j)

        if disp:
            print "%4d %4d   Assign       " %\
                    (cur, line),
            print repr(A[cur:end])

        assign = col.Assign(parent)
        assign.cur = cur
        assign.line = line
        assign.code = A[cur:end]

        k = cur
        cur, line = create_assign_variable(assign, cur, line, eq_loc)

        cur += 1
        while A[cur] in " \t":
            cur += 1

        assert A[cur] == "="

        k = cur+1
        while A[k] in " \t":
            k += 1

        assert len(assign) == 1

        cur_, line = create_expression(assign, k, line)

        assert len(assign) == 2

        return cur_, line



    def create_assign_variable(node, cur, line, end=None):

        assert A[cur] in letters

        k = cur+1
        while A[k] in letters+digits+"_":
            k += 1

        name = A[cur:k]
        last = k

        while A[k] in " \t":
            k += 1

        # Set value of cell
        if A[k] == "{":

            node = col.Cset(node, name)
            node.cur = cur
            node.line = line

            while A[k] == "{":

                last, line = fill_cell(node, k, line)
                k += last + 1
                while A[k] in " \t":
                    k += 1

            node.code = A[cur:last+1]

            if disp:
                print "%4d %4d     Cset       " %\
                        (cur, line),
                print repr(A[cur:last+1])

            cur = last

        # Set value of array
        elif A[k] == "(":

            node = col.Set(node, name)
            node.cur = cur
            node.line = line

            end = findend_paren(k)

            if disp:
                print "%4d %4d     Set        " %\
                        (cur, line),
                print repr(A[cur:end+1])

            node.code = A[cur:end+1]

            last, line = create_list(node, k, line)
            cur = last

        # Simple variable assignment
        elif A[k] == "=":

            if disp:
                print "%4d %4d     Var        " % (cur, line),
                print repr(A[cur:last])


            node = col.Var(node, name)
            node.cur = cur
            node.line = line
            node.code = A[cur:last]

            cur = last

        elif A[k] == ".":

            k += 1

            # Fieldname of type "a.() = ..."
            if A[k] == "(":

                end = findend_paren(k)

                k += 1

                while A[k] in " \t":
                    k += 1

                if disp:
                    print "%4d %4d     Nset     " % (cur, line),
                    print repr(A[cur:end+1])


                node = col.Nset(node, name)
                node.cur = cur
                node.line = line
                node.code = A[cur:end+1]

                cur, line = create_expression(node, cur, line)
                cur += 1


            elif A[k] in letters:

                j = k+1
                while A[j] in letters+digits+"_":
                    j += 1

                sname = A[k:j]
                last = j

                while A[j] in " \t":
                    j += 1

                # Fieldname of type "a.b(...) = ..."
                if A[j] == "(":

                    end = findend_paren(j)
                    if disp:
                        print "%4d %4d     Fset     " % (cur, line),
                        print repr(A[cur:end+1])

                    node = col.Fset(node, name, sname)
                    node.cur = cur
                    node.line = line
                    node.code = A[cur:end+1]

                    cur, line = create_expression(node, j+1, line,
                            end=end)

                # Fieldname of type "a.b = ..."
                else:

                    if disp:
                        print "%4d %4d     Fvar     " % (cur, line),
                        print repr(A[cur:last+1])

                    node = col.Fvar(node, name, sname)
                    node.cur = cur
                    node.line = line
                    node.code = A[cur:last+1]


        else:
            assert False

        return cur, line


    def fill_cell(cset, cur, line):

        assert A[cur] == "{"

        cur = cur+1

        while True:

            if A[cur] == "}":
                return cur, line

            elif A[cur] in expression_start:

                cur, line = create_expression(cset, cur, line)

                cur += 1
                while A[cur] in " \t":
                    cur += 1

                return cur, line

            elif A[cur] == " ":
                pass

            cur += 1


    def create_matrix(node, cur, line):

        assert A[cur] == "["

        end = findend_matrix(cur)
        if disp:
            print "%4s %4s     Matrix     " % (cur, line),
            print repr(A[cur:end+1])

        L = iterate_list(cur)
        matrix = col.Matrix(node)
        matrix.cur = cur
        matrix.line = line
        matrix.code = A[cur:end+1]

        inter = -1
        for array in L:

            start = array[0][0]
            end = array[-1][-1]

            vector = col.Vector(matrix)
            vector.cur = start
            vector.line = line
            vector.code = A[start:end]

            if disp:
                print "%4s %4s     Vector     " % (start, line),
                print repr(A[start:end])

            for start,end in array:

                create_expression(vector, start, line, end)

                if inter != -1:
                    line += A.count("\n", inter, start)

                inter = end-1

        return findend_matrix(cur), line


    def create_for(parent, cur, line):

        assert A[cur:cur+3] == "for"

        start = cur

        if disp:
            print "%4d %4d   For" % (cur, line),
            print A[cur:A.find("\n", cur)+1]

        for_loop = col.For(parent)
        for_loop.cur = cur
        for_loop.line = line

        k = cur+3
        while A[k] in "( \t":
            k += 1

        cur, line = create_variable(for_loop, k, line)

        k += 1
        while A[k] in " \t":
            k += 1

        assert A[k] == "="
        k += 1

        while A[k] in " \t":
            k += 1

        cur, line = create_expression(for_loop, k, line)
        cur += 1

        while A[k] in ") \t":
            k += 1

        if A[k] == ",":
            k += 1

        while A[k] in " \t\n;":
            if A[k] == "\n":
                line += 1
            k += 1

        block = col.Block(for_loop)
        block.cur = k
        block.line = line
        end, line = fill_codeblock(block, k, line)

        for_loop.code = A[start:end]
        block.code = A[k:end]

        return end, line


    def create_while(parent, cur, line):
        raise NotImplementedError
        if disp:
            print "%4d %4d   While" % (cur, line)

    def create_switch(parent, cur, line):
        raise NotImplementedError
        if disp:
            print "%4d %4d   Switch" % (cur, line)

    def create_try(parent, cur, line):
        raise NotImplementedError
        if disp:
            print "%4d %4d   Try" % (cur, line)

    def create_cell(parent, cur, line):
        raise NotImplementedError

    def create_variable(parent, cur, line):

        assert A[cur] in letters

        k = cur+1
        while A[k] in letters+digits+"_":
            k += 1

        name = A[cur:k]
        last = k

        while A[k] in " \t":
            k += 1

        # Get value of cell
        if A[k] == "{":

            end = findend_cells(k)

            node = col.Cget(parent, name)
            node.cur = cur
            node.line = line
            node.code = A[cur:end+1]

            if disp:
                print "%4d %4d     Cget  " % (cur, line),
                print repr(A[cur:end+1])

            while A[k] == "{":

                cur, line = fill_cell(node, k, line)
                k = cur+1
                while A[k] in " \t":
                    k += 1


        # Get value of array
        elif A[k] == "(":

            end = findend_paren(k)

            if disp:
                print "%4d %4d     Get        " % (cur, line),
                print repr(A[cur:end+1])

            node = col.Get(parent, name)
            node.cur = cur
            node.line = line
            node.code = A[cur:end+1]

            cur, line = create_list(node, k, line)


        elif A[k] == "." and A[k+1] not in "*/\\^'":

            k += 1

            # Fieldname of type "a.(..)"
            if A[k] == "(":

                if disp:
                    print "%4d %4d     Nget  " % (cur, line),
                    end = findend_paren(k)
                    print A[cur:end+1]

                k += 1

                while A[k] in " \t":
                    k += 1

                node = col.Nget(parent, name)
                node.cur = cur
                node.line = line
                node.code = A[cur:end+1]

                cur, line = create_expression(node, cur, line)


            elif A[k] in letters:

                j = k+1
                while A[j] in letters+digits+"_":
                    j += 1

                sname = A[k:j]
                last = j

                while A[j] in " \t":
                    j += 1

                # Fieldname of type "a.b(...)"
                if A[j] == "(":

                    if disp:
                        print "%4d %4d     Fget  " % (cur, line),
                        end = findend_paren(j)
                        print A[cur:end+1]


                    node = col.Fget(parent, name, sname)
                    node.cur = cur
                    node.line = line
                    node.code = A[cur:end+1]

                    j += 1
                    while A[j] in " \t":
                        j += 1

                    cur, line = create_expression(node, j, line)

                # Fieldname of type "a.b"
                else:

                    if disp:
                        print "%4d %4d     Fvar  " % (cur, line),
                        print A[cur:last+1]

                    node = col.Fvar(parent, name, sname)
                    node.cur = cur
                    node.line = line
                    node.code = A[cur:last+1]

                    cur = last

                assert False

        # Simple variable
        else:

            if disp:
                print "%4d %4d     Var        " % (cur, line),
                print repr(A[cur:last])

            node = col.Var(parent, name)
            node.cur = cur
            node.line = line
            node.code = A[cur:last]

        node.declare()

        while A[cur] in " \t":
            cur += 1

        return cur, line


    def create_comment(parent, cur, line):

        end = findend_comment(cur)
        line += A.count("\n", cur, end+1)

        if disp:
            print "%4d %4d   Comment      " % (cur, line),
            print repr(A[cur:end])

        return end, line


    def create_string(parent, cur, line):

        end = findend_string(cur)
        assert "\n" not in A[cur:end]
        string = col.String(parent, A[cur+1:end])
        string.code = A[cur:end+1]

        if disp:
            print "%4d %4d   String " % (cur, line),
            print repr(A[cur:end+1])

        return end, line


    def create_list(parent, cur, line):

        assert A[cur] == "("

        end = cur+1
        for vector in iterate_comma_list(cur):
            for start,end in vector:
                _, line = create_expression(parent, start, line, end)

        return end, line



    def create_number(node, start, line):

        assert A[start] in digits or\
                A[start] == "." and A[start+1] in digits

        k = start

        while A[k] in digits:
            k += 1
        last = k-1

        integer = True
        if A[k] == ".":
            integer = False

            k += 1
            while A[k] in digits:
                k += 1
            last = k-1

        if A[k] in "eEdD":

            exp = k

            k = k+1
            if A[k] in "+-":
                k += 1

            while A[k] in digits:
                k += 1

            number = A[start:exp] + "e" + A[exp+1:k]

            last = k-1

            if A[k] in "ij":

                k += 1
                node = col.Ifloat(node, number)
                if disp:
                    print "%4d %4d     Ifloat     " % (start, line),
                    print repr(A[start:last+1])

            else:
                node = col.Float(node, number)
                if disp:
                    print "%4d %4d     Float      " % (start, line),
                    print repr(A[start:last+1])

        elif integer:

            number = A[start:k]

            if A[k] in "ij":

                k += 1
                node = col.Iint(node, A[start:k])
                if disp:
                    print "%4d %4d     Iint       " % (start, line),
                    print repr(A[start:last+1])

            else:
                node = col.Int(node, A[start:k])
                if disp:
                    print "%4d %4d     Int        " % (start, line),
                    print repr(A[start:last+1])

        else:

            if A[k] in "ij":

                node = col.Ifloat(node, A[start:k])
                k += 1
                if disp:
                    print "%4d %4d     Ifloat     " % (start, line),
                    print repr(A[start:last+1])

            else:
                node = col.Float(node, A[start:k])
                if disp:
                    print "%4d %4d     Float      " % (start, line),
                    print repr(A[start:last+1])

        node.cur = start
        node.code = A[start:last+1]
        node.line = line

        return k-1, line

    def create_lambda(node, start, line):

        assert A[start] == "@"

        parent = node.parent
        if parent["class"] == "Assign" and parent[1] is node:
            name = parent[0]["name"]
        else:
            name = "lambda"

        program = node.program
        name = "_%s_%03d" % (name, len(program))

        func = col.Func(program, name)
        func.cur = start
        func.line = line

        declares = col.Declares(func)
        returns = col.Returns(func)
        params = col.Params(func)

        k = start+1
        while A[k] in " \t":
            k += 1

        assert A[k] == "("

        end = findend_paren(k)

        end += 1
        while A[end] in " \t":
            end += 1
        cur = end
        end = findend_expression(end)

        if disp:
            print "%4d %4d     Lambda     " % (start, line),
            print repr(A[start:end+1])

        _, line = create_list(params, k, line)

        block = col.Block(func)
        assign = col.Assign(block)
        var = col.Var(assign, "_retval")

        cur, line = create_expression(assign, cur, line, end=end)

        func["backend"] = "func_lambda"
        returns["backend"] = "func_lambda"
        params["backend"] = "func_lambda"
        declares["backend"] = "func_lambda"

        var = col.Var(returns, "_retval")
        var.declare()

        lamb = col.Lambda(node, name)
        lamb.type = "func_lambda"
        lamb.declare()



    def create_expression(node, start, line, end=None, start_opr=None):

        assert A[start] in expression_start

        if A[start] == ":":

            if disp:
                print "%4s %4s     Expression " % (start, line),
                print repr(A[start:start+1])
                print "%4s %4s     All        " % (start, line),
                print repr(A[start:start+1])

            col.All(node)
            return start, line

        if end is None:
            end = findend_expression(start)
        else:
            assert isinstance(end, int)

        if disp:
            print "%4s %4s     Expression " % (start, line),
            print repr(A[start:end])


        operators = [
            "||", "&&", "|", "&",
            "~=", "==", ">=", ">", "<=", "<",
            ":", "+", "-",
            ".*", "*", "./", "/", ".\\", "\\",
            ".^", "^"]

        if not (start_opr is None):
            operators = operators[operators.index(start_opr)+1:]

        for opr in operators:

            # Pre-screen
            if opr not in A[start:end]:
                continue

            starts = [start]
            ends = []

            k = start
            while True:

                if A[k] == "(":
                    k = findend_paren(k)

                elif A[k] == "[":
                    k = findend_matrix(k)

                elif A[k] == "'":

                    if A[k-1] != ".":

                        j = k-1
                        while A[j] in " \t":
                            k -= 1

                        if A[j] not in letters+digits+")]}":
                            k = findend_string(k)

                elif opr == A[k]:

                    j = k-1
                    while A[j] in " \t":
                        j -= 1

                    # no prefixes
                    if opr in "+-" and A[j] not in letters+digits+")]}":
                        continue

                    # no (scientific) numbers
                    if A[k-1] in "dDeE" and A[k+1] in digits:
                        continue

                    while A[k+1] in " \t":
                        k += 1

                    starts.append(k+1)
                    ends.append(j+1)

                k += 1
                if k >= end:
                    ends.append(k)
                    break

            if len(ends)>1:

                node = retrieve_operator(opr)(node)
                node.cur = start
                node.line = line
                node.code = A[starts[0]:ends[-1]+1]

                for s,e in zip(starts, ends):
                    create_expression(node, s, line, e, opr)

                return end, line

        # All operators removed at this point!

        if A[end] in expression_end:
            end -= 1

        while A[end] in " \t":
            end -= 1

        END = end

        if A[start] == "'":
            assert A[end] == "'"
            assert "\n" not in A[start:end+1]

            string = col.String(node, A[start+1:end])
            string.cur = start
            string.line = line
            string.code = A[start:end+1]

        # Prefixes
        while A[start] in "-~":

            if A[start] == "-":

                node = col.Neg(node)
                node.cur = start
                node.line = line
                node.code = A[start:end+1]

                start += 1

            if A[start] == "~":

                node = col.Not(node)
                node.cur = start
                node.line = line
                node.code = A[start:end+1]
                start += 1

            while A[start] in " \t":
                start += 1

        # Postfixes
        if A[end] == "'":
            if A[end-1] == ".":
                node = col.Transpose(node)
                node.cur = start
                node.line = line
                node.code = A[start:end+1]
                end -= 2
            else:
                node = col.Ctranspose(node)
                node.cur = start
                node.line = line
                node.code = A[start:end+1]
                end -= 1

            while A[end] in " \t":
                end -= 1

        # Parenthesis
        if A[start] == "(":
            assert A[end] == ")"

            node = col.Paren(node)
            node.cur = start
            node.line = line
            node.code = A[start:end+1]

            start += 1
            while A[start] in " \t":
                start += 1

            end -= 1
            while A[end] in " \t":
                end -= 1

            return create_expression(node, start, line, end)

        # Reserved keywords
        elif A[start:start+3] == "end" and\
                A[start+3] in " \t" + expression_end:
            node = col.End(node)
            node.cur = start
            node.line = line
            node.code = A[start:start+3]

        elif A[start:start+6] == "return" and A[start+6] in " ,;\n":
            node = col.Return(node)
            node.cur = start
            node.line = line
            node.code = A[start:start+6]

        elif A[start:start+5] == "break" and A[start+5] in " ,;\n":
            node = col.Break(node)
            node.cur = start
            node.line = line
            node.code = A[start:start+5]


        # Rest
        elif A[start] in digits or\
                A[start] == "." and A[start+1] in digits:
            cur, line = create_number(node, start, line)

        elif A[start] == "[":
            cur, line = create_matrix(node, start, line)

        elif A[start] == "{":
            cur, line = create_cell(node, start, line)

        else:
            assert A[start] in letters
            cur, line = create_variable(node, start, line)


        return END, line


    def retrieve_operator(opr):

        if opr == "^":      return col.Exp
        elif opr == ".^":   return col.Elexp
        elif opr == "\\":   return col.Rdiv
        elif opr == ".\\":  return col.Elrdiv
        elif opr == "/":    return col.Div
        elif opr == "./":   return col.Rdiv
        elif opr == "*":    return col.Mul
        elif opr == ".*":   return col.Elmul
        elif opr == "+":    return col.Plus
        elif opr == "-":    return col.Minus
        elif opr == ":":    return col.Colon
        elif opr == "<":    return col.Lt
        elif opr == "<=":   return col.Le
        elif opr == ">":    return col.Gt
        elif opr == ">=":   return col.Ge
        elif opr == "==":   return col.Eq
        elif opr == "~=":   return col.Ne
        elif opr == "&":    return col.Band
        elif opr == "|":    return col.Bor
        elif opr == "&&":   return col.Land
        elif opr == "||":   return col.Lor


    def iterate_list(start):

        assert A[start] in list_start

        k = start+1
        while A[k] in " \t":
            k += 1

        assert A[k] in expression_start

        while True:

            if A[k] == "(":
                k = findend_paren(k)

            elif A[k] == "[":
                k = findend_matrix(k)

            elif A[k] == "'":
                k = findend_string(k)

            elif A[k:k+3] == "...":
                k = findend_dots(k)

            elif A[k] in expression_end:
                if A[k] in ",;":
                    return iterate_comma_list(start)
                else:
                    return iterate_space_list(start)


            k += 1

    def iterate_comma_list(start):

        k = start+1
        assert A[k] in expression_start

        starts = [[k]]
        ends = [[]]

        while True:

            if A[k] == "(":
                k = findend_paren(k)

            elif A[k] == "[":
                k = findend_matrix(k)

            elif A[k] == "'":
                k = findend_string(k)

            elif A[k:k+3] == "...":
                k = findend_dots(k)

            elif A[k] in expression_end:

                ends[-1].append(k)
                if A[k] == ",":

                    while A[k+1] in " \t":
                        k += 1
                    starts[-1].append(k+1)

                elif A[k] == ";":

                    while A[k+1] in " \t":
                        k += 1
                    starts.append([k+1])
                    ends.append([])

                else:
                    out = [zip(starts[i], ends[i])\
                            for i in xrange(len(ends))]
                    return out

            k += 1

    def iterate_space_list(start):

        k = start
        assert A[k] in expression_start

        starts = [[k]]
        ends = [[]]

        while True:

            if A[k] == "(":
                k = findend_paren(k)

            elif A[k] == "[":
                k = findend_matrix(k)

            elif A[k] == "'":
                k = findend_string(k)

            elif A[k:k+3] == "...":
                k = findend_dots(k)

            elif A[k] in " \t":

                while A[k] in " \t":
                    k += 1

                if A[k:k+2] in operator2:
                    k += 1

                elif A[k] in "+-":

                    if A[k+1] in expression_start:
                        ends[-1].append(k-1)
                        starts[-1].append(k)


                    elif A[k+1] in " \t":
                        while A[k+1] in " \t":
                            k += 1

                elif A[k] in operator1:
                    while A[k+1] in " \t":
                        k += 1

                else:
                    assert False

            elif A[k] == "\n":

                ends[-1].append(k-1)
                while A[k+1] in " \t":
                    k += 1
                starts.append([k+1])
                ends.append([])


            elif A[k] in expression_end:

                ends[-1].append(k)
                if A[k] == ",":

                    while A[k+1] in " \t":
                        k += 1
                    starts[-1].append(k+1)

                elif A[k] == ";":

                    while A[k+1] in " \t":
                        k += 1
                    ends.append([])
                    starts.append([k+1])

                else:
                    out = [zip(starts[i], ends[i])\
                            for i in xrange(len(ends))]
                    return out

            k += 1



    def findend_expression(start):

        assert A[start] in expression_start
        k = start

        while True:

            if A[k] == "(":
                k = findend_paren(k)

            elif A[k] == "[":
                k = findend_matrix(k)

            elif A[k] == "'":
                k = findend_string(k)

            elif A[k] == "=":

                if A[k+1] == "=":
                    k += 1
                else:
                    return k

            elif A[k] in expression_end:
                return k

            k += 1


    def findend_matrix(start):
        "find index to end of matrix"

        assert A[start] == "["
        bracecount = 1
        k = start+1

        while True:

            if A[k] == "[":
                bracecount += 1

            elif A[k] == "]":
                bracecount -= 1
                if not bracecount:
                    return k

            elif A[k] == "%":
                k = findend_comment(k)

            elif A[k] == "'":
                k = findend_string(k)

            k += 1

    def findend_string(start):
        "find index to end of string"

        assert A[start] == "'"

        k = A.find("'", start+1)
        assert k != -1

        while A[k-1] == "\\":
            k = A.find("'", k+1)
            assert k != -1

        assert A.find("\n", start, k) == -1
        return k

    def findend_comment(start):
        "find index to end of comment"

        assert A[start] == "%"

        # blockcomment
        if A[start+1] == "{":
            eoc = A.find("%}", start+2)
            assert eoc>-1
            return eoc+1

        # Linecomment
        eoc = A.find("\n", start)
        assert eoc>-1
        return eoc

    def findend_dots(start):

        assert A[start:start+3] == "..."
        k = A.find("\n", start)
        assert k != -1
        return k

    def findend_paren(start):

        assert A[start] == "("

        k = start+1
        while True:

            if A[k] == "%":
                assert False
            elif A[k] == "'":
                k = findend_string(k)
            elif A[k] == "(":
                k = findend_paren(k)
            elif A[k] == ")":
                return k

            k += 1

    def findend_cells(start):
        assert A[start] == "{"

        k = start
        while True:

            if A[k] == "%":
                assert False
            elif A[k] == "'":
                k = findend_string(k)
            elif A[k] == "(":
                k = findend_paren(k)
            elif A[k] == "[":
                k = findend_matrix(k)
            elif A[k] == "}":
                l = k+1
                while A[l] in " \t":
                    l += 1
                if A[l] != "{":
                    return k
                k = l

            k += 1

    prog = create_program()

    return prog


if __name__ == "__main__":

    test_code = """
function y = test_filtfilt(b,a,x)
    [nt,nx] = size(x);
    y = zeros(nt,nx);
    for k=1:nx
       y(:,k) = flipud(filteric1D(b,a, flipud(filteric1D(b,a,x(:,k)))));

function y = filteric1D(b,a,x)
  np = size(x,1);
  y = zeros(np,1);
  ord = length(b);
  for i=1:np
      y(i) = b(1)*x(i);
      for j = 1:(min(ord,i)-1)
          y(i) = y(i) + b(j+1) * x(i - j)
      end
  end
end

n = 10
b = rand(n)
a = rand(n)
x = rand(n,n)
y = test_filtfilt(b, a, x)
            """
    test_code = "[1,2,3]"
    tree = process(test_code)

#      print
#      tree.generate(False)
#      tree.configure()
    print tree.summary()
#      print tree.generate(False)
    print test_code
