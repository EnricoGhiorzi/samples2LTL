from z3 import *
import pdb
from utils.SimpleTree import SimpleTree, Formula

class DagSATEncoding:
    """
    - D is the depth of the tree
    - lassoStartPosition denotes the position when the trace values start looping
    - traces is 
      - list of different recorded values (trace)
      - each trace is a list of recordings at time units (time point)
      - each time point is a list of variable values (x1,..., xk)
    """
    def __init__(self, D, testTraces): 
        
        # Compute (maximum) length of traces
        time_length = 0;
        for trace in testTraces.acceptedTraces + testTraces.rejectedTraces:
            if trace.lengthOfTrace > time_length:
                time_length = trace.lengthOfTrace

        # Add parametrized operators
        self.listOfOperators = ['⊥', '!', '&','|', 'X', 'G', 'R']
        self.zeroaryOperators = ['⊥']
        self.unaryOperators = ['G', '!', 'X']
        self.binaryOperators = ['&', '|', 'R']
        for t in range(0, time_length):
            self.listOfOperators.extend(['G≤'+str(t), 'G>'+str(t), 'U≤'+str(t), 'F≤'+str(t), 'R≤'+str(t), 'R>'+str(t)])
            self.unaryOperators.extend(['G≤'+str(t), 'G>'+str(t), 'F≤'+str(t)])
            self.binaryOperators.extend(['U≤'+str(t), 'R≤'+str(t), 'R>'+str(t)])

        #except for the operators, the nodes of the "syntax table" are additionally the propositional variables 

        # Use default operators only
        # if testTraces.operators == None:
        #     self.listOfOperators = defaultOperators
        # else:
        #     self.listOfOperators = testTraces.operators
        
        if 'prop' in self.listOfOperators:
            self.listOfOperators.remove('prop')

        # self.unaryOperators = [op for op in self.listOfOperators if op in unary]
        # self.binaryOperators = [op for op in self.listOfOperators if op in binary]
        
        # self.noneOperator = 'none' # a none operator is not needed in this encoding
        
        self.solver = Solver()
        
        
        self.formulaDepth = D
        
        
        #traces = [t.traceVector for t in testTraces.acceptedTraces + testTraces.rejectedTraces]
        
        self.traces = testTraces

        self.listOfVariables = [i for i in range(self.traces.numVariables)]
        
        
        
        
        #keeping track of which positions in a tree (and in time) are visited, so that constraints are not generated twice
#        self.visitedPositions = set()


    def getInformativeVariables(self):
        res = []
        res += [v for v in self.x.values()]
        res += [v for v in self.l.values()]
        res += [v for v in self.r.values()]


        return res
    """    
    the working variables are 
        - x[i][o]: i is a subformula (row) identifier, o is an operator or a propositional variable. Meaning is "subformula i is an operator (variable) o"
        - l[i][j]:  "left operand of subformula i is subformula j"
        - r[i][j]: "right operand of subformula i is subformula j"
        - y[i][tr][t]: semantics of formula i in time point t of trace tr
    """
    def encodeFormula(self, unsatCore=True):
        self.operatorsAndVariables = self.listOfOperators + self.listOfVariables
        
        self.x = { (i, o) : Bool('x_'+str(i)+'_'+str(o)) for i in range(self.formulaDepth) for o in self.operatorsAndVariables }
        self.l = {(parentOperator, childOperator) : Bool('l_'+str(parentOperator)+'_'+str(childOperator))\
                                                 for parentOperator in range(1, self.formulaDepth)\
                                                 for childOperator in range(parentOperator)}
        self.r = {(parentOperator, childOperator) : Bool('r_'+str(parentOperator)+'_'+str(childOperator))\
                                                 for parentOperator in range(1, self.formulaDepth)\
                                                 for childOperator in range(parentOperator)}

        self.y = { (i, traceIdx, positionInTrace) : Bool('y_'+str(i)+'_'+str(traceIdx)+'_'+str(positionInTrace))\
                  for i in range(self.formulaDepth)\
                  for traceIdx, trace in enumerate(self.traces.acceptedTraces + self.traces.rejectedTraces)\
                  for positionInTrace in range(trace.lengthOfTrace)}
        
        
        self.solver.set(unsat_core=unsatCore)

        self.exactlyOneOperator()       
        self.firstOperatorVariable()

        self.propVariablesSemantics()
         
        self.operatorsSemantics()
        self.noDanglingVariables()

        # Ensure formulae are syntactically safe
        self.onlyNegateAtoms()
        
        self.solver.assert_and_track(And( [ self.y[(self.formulaDepth - 1, traceIdx, 0)] for traceIdx in range(len(self.traces.acceptedTraces))] ), 'accepted traces should be accepting')
        self.solver.assert_and_track(And( [ Not(self.y[(self.formulaDepth - 1, traceIdx, 0)]) for traceIdx in range(len(self.traces.acceptedTraces), len(self.traces.acceptedTraces+self.traces.rejectedTraces))] ),\
                                     'rejecting traces should be rejected')
        
        
    
    
    def propVariablesSemantics(self):
        for i in range(self.formulaDepth):
            for p in self.listOfVariables:
                for traceIdx, tr in enumerate(self.traces.acceptedTraces + self.traces.rejectedTraces):
                    self.solver.assert_and_track(Implies(self.x[(i, p)],\
                                                          And([ self.y[(i,traceIdx, timestep)] if tr.traceVector[timestep][p] == True else Not(self.y[(i, traceIdx, timestep)])\
                                                               for timestep in range(tr.lengthOfTrace)])),\
                                                          "semantics of propositional variable depth_"+str(i)+' var _'+str(p)+'_trace_'+str(traceIdx))
                    
            

        
    
    def firstOperatorVariable(self):
        self.solver.assert_and_track(Or([self.x[k] for k in self.x if k[0] == 0 and k[1] in self.listOfVariables + self.zeroaryOperators]),\
                                     'first operator a variable or a zeroary operator')

    def noDanglingVariables(self):
        if self.formulaDepth > 0:
            self.solver.assert_and_track(
                And([
                    Or(
                        AtLeast([self.l[(rowId, i)] for rowId in range(i+1, self.formulaDepth)]+ [1]),
                        AtLeast([self.r[(rowId, i)] for rowId in range(i+1, self.formulaDepth)] + [1])
                    )
                    for i in range(self.formulaDepth - 1)]
                ),
                "no dangling variables"
            )
    
    def exactlyOneOperator(self):
            
            
            self.solver.assert_and_track(And([\
                                              AtMost( [self.x[k] for k in self.x if k[0] == i] +[1])\
                                              for i in range(self.formulaDepth)\
                                              ]),\
                                              "at most one operator per subformula"\
            )
            
            self.solver.assert_and_track(And([\
                                              AtLeast( [self.x[k] for k in self.x if k[0] == i] +[1])\
                                              for i in range(self.formulaDepth)\
                                              ]),\
                                              "at least one operator per subformula"\
            )
            
            if (self.formulaDepth > 0):
                self.solver.assert_and_track(And([\
                                                Implies(
                                                    Or(
                                                        [self.x[(i, op)] for op in self.binaryOperators+self.unaryOperators]
                                                    ),
                                                    AtMost( [self.l[k] for k in self.l if k[0] == i] +[1])\
                    )
                                              for i in range(1,self.formulaDepth)\
                                              ]),\
                                              "at most one left operator for binary and unary operators"\
            )

            if (self.formulaDepth > 0):
                self.solver.assert_and_track(And([\
                                                Implies(
                                                    Or(
                                                        [self.x[(i, op)] for op in
                                                         self.binaryOperators + self.unaryOperators]
                                                    ),
                                                    AtLeast( [self.l[k] for k in self.l if k[0] == i] +[1])\
                                                    )
                                              for i in range(1,self.formulaDepth)\
                                              ]),\
                                              "at least one left operator for binary and unary operators"\
            )

            if (self.formulaDepth > 0):
                self.solver.assert_and_track(And([ \
                    Implies(
                        Or(
                            [self.x[(i, op)] for op in self.binaryOperators]
                        ),
                        AtMost([self.r[k] for k in self.r if k[0] == i] + [1]) \
                        )
                    for i in range(1, self.formulaDepth) \
                    ]), \
                    "at most one right operator for binary" \
                    )

            if (self.formulaDepth > 0):
                self.solver.assert_and_track(And([ \
                    Implies(
                        Or(
                            [self.x[(i, op)] for op in
                             self.binaryOperators]
                        ),
                        AtLeast([self.r[k] for k in self.r if k[0] == i] + [1]) \
                        )
                    for i in range(1, self.formulaDepth) \
                    ]), \
                    "at least one right operator for binary" \
                    )

            if (self.formulaDepth > 0):
                self.solver.assert_and_track(And([ \
                    Implies(
                        Or(
                            [self.x[(i, op)] for op in
                             self.unaryOperators]
                        ),
                        Not(
                            Or([self.r[k] for k in self.r if k[0] == i]) \
                        )
                    )
                    for i in range(1, self.formulaDepth) \
                    ]), \
                    "no right operators for unary" \
                    )

            if (self.formulaDepth > 0):
                self.solver.assert_and_track(And([ \
                    Implies(
                        Or(
                            [self.x[(i, op)] for op in
                             self.listOfVariables + self.zeroaryOperators]
                        ),
                        Not(
                            Or(
                                Or([self.r[k] for k in self.r if k[0] == i]), \
                                Or([self.l[k] for k in self.l if k[0] == i])
                            )

                        )
                    )
                    for i in range(1, self.formulaDepth) \
                    ]), \
                    "no left or right children for variables or zeroary operators" \
                    )


    def onlyNegateAtoms(self):
        self.solver.assert_and_track(And([ \
            Implies( \
                self.x[(i, '!')], \
                Or([ \
                    And([self.l[(i, leftArg)], Or([self.x[(leftArg, prop)] for prop in self.listOfVariables])]) \
                for leftArg in range(i)])
            )\
            for i in range(self.formulaDepth)
        ]), "only atomic propositions can be negated")


    def operatorsSemantics(self):

        for traceIdx, tr in enumerate(self.traces.acceptedTraces + self.traces.rejectedTraces):

            # For NOT operator we need to start from i=0
            if '⊥' in self.listOfOperators:
                for i in range(self.formulaDepth):
                    self.solver.assert_and_track(Implies(self.x[(i, '⊥')],\
                        And([ Not(self.y[(i, traceIdx, timestep)]) for timestep in range(tr.lengthOfTrace)])\
                    ),\
                    'semantics of false for trace %d and depth %d'%(traceIdx, i))

            for i in range(1, self.formulaDepth):
                
                if '|' in self.listOfOperators:
                    #disjunction
                     self.solver.assert_and_track(Implies(self.x[(i, '|')],\
                                                            And([ Implies(\
                                                                           And(\
                                                                               [self.l[i, leftArg], self.r[i, rightArg]]\
                                                                               ),\
                                                                           And(\
                                                                               [ self.y[(i, traceIdx, timestep)]\
                                                                                ==\
                                                                                Or(\
                                                                                   [ self.y[(leftArg, traceIdx, timestep)],\
                                                                                    self.y[(rightArg, traceIdx, timestep)]]\
                                                                                   )\
                                                                                 for timestep in range(tr.lengthOfTrace)]\
                                                                               )\
                                                                           )\
                                                                          for leftArg in range(i) for rightArg in range(i) ])),\
                                                             'semantics of disjunction for trace %d and depth %d'%(traceIdx, i))
                
                if '&' in self.listOfOperators:
                      #conjunction
                     self.solver.assert_and_track(Implies(self.x[(i, '&')],\
                                                            And([ Implies(\
                                                                           And(\
                                                                               [self.l[i, leftArg], self.r[i, rightArg]]\
                                                                               ),\
                                                                           And(\
                                                                               [ self.y[(i, traceIdx, timestep)]\
                                                                                ==\
                                                                                And(\
                                                                                   [ self.y[(leftArg, traceIdx, timestep)],\
                                                                                    self.y[(rightArg, traceIdx, timestep)]]\
                                                                                   )\
                                                                                 for timestep in range(tr.lengthOfTrace)]\
                                                                               )\
                                                                           )\
                                                                          for leftArg in range(i) for rightArg in range(i) ])),\
                                                             'semantics of conjunction for trace %d and depth %d'%(traceIdx, i))
                     
                if '->' in self.listOfOperators:
                       
                      #implication
                     self.solver.assert_and_track(Implies(self.x[(i, '->')],\
                                                            And([ Implies(\
                                                                           And(\
                                                                               [self.l[i, leftArg], self.r[i, rightArg]]\
                                                                               ),\
                                                                           And(\
                                                                               [ self.y[(i, traceIdx, timestep)]\
                                                                                ==\
                                                                                Implies(\
                                                                                  self.y[(leftArg, traceIdx, timestep)],\
                                                                                  self.y[(rightArg, traceIdx, timestep)]\
                                                                                   )\
                                                                                 for timestep in range(tr.lengthOfTrace)]\
                                                                               )\
                                                                           )\
                                                                          for leftArg in range(i) for rightArg in range(i) ])),\
                                                             'semantics of implication for trace %d and depth %d'%(traceIdx, i))
                if '!' in self.listOfOperators:
                      #negation
                     self.solver.assert_and_track(Implies(self.x[(i, '!')],\
                                                           And([\
                                                               Implies(\
                                                                         self.l[(i,onlyArg)],\
                                                                         And([\
                                                                              self.y[(i, traceIdx, timestep)] == Not(self.y[(onlyArg, traceIdx, timestep)])\
                                                                              for timestep in range(tr.lengthOfTrace)\
                                                                              ])\
                                                                          )\
                                                               for onlyArg in range(i)\
                                                               ])\
                                                           ),\
                                                   'semantics of negation for trace %d and depth %d' % (traceIdx, i)\
                                                   )
                if 'G' in self.listOfOperators:
                      #globally                
                     self.solver.assert_and_track(Implies(self.x[(i, 'G')],\
                                                           And([\
                                                               Implies(\
                                                                         self.l[(i,onlyArg)],\
                                                                         And([\
                                                                              self.y[(i, traceIdx, timestep)] ==\
                                                                              And([self.y[(onlyArg, traceIdx, futureTimestep)] for futureTimestep in tr.futurePos(timestep) ])\
                                                                              for timestep in range(tr.lengthOfTrace)\
                                                                              ])\
                                                                          )\
                                                               for onlyArg in range(i)\
                                                               ])\
                                                           ),\
                                                   'semantics of globally operator for trace %d and depth %d' % (traceIdx, i)\
                                                   )
                
                # Parametrized globally
                d = 0
                while 'G≤'+str(d) in self.listOfOperators:
                    operator = 'G≤'+str(d)
                    self.solver.assert_and_track(Implies(self.x[(i, operator)],\
                        And([\
                            Implies(\
                                self.l[(i,onlyArg)],\
                                And([\
                                    self.y[(i, traceIdx, timestep)] ==\
                                    And([self.y[(onlyArg, traceIdx, futureTimestep)] for futureTimestep in tr.futurePos(timestep)[:d+1]])\
                                    for timestep in range(tr.lengthOfTrace)\
                                    ])\
                                )\
                            for onlyArg in range(i)\
                        ])\
                    ),\
                    'semantics of parametrized globally(≤%d) operator for trace %d and depth %d' % (d, traceIdx, i)\
                    )
                    d += 1

                d = 0
                while 'G>'+str(d) in self.listOfOperators:
                    operator = 'G>'+str(d)
                    self.solver.assert_and_track(Implies(self.x[(i, operator)],\
                        And([\
                            Implies(\
                                self.l[(i,onlyArg)],\
                                And([\
                                    self.y[(i, traceIdx, timestep)] ==\
                                    And([self.y[(onlyArg, traceIdx, futureTimestep)] for futureTimestep in tr.futurePos(timestep)[d+1:]])\
                                    for timestep in range(tr.lengthOfTrace)\
                                    ])\
                                )\
                            for onlyArg in range(i)\
                        ])\
                    ),\
                    'semantics of parametrized globally(>%d) operator for trace %d and depth %d' % (d, traceIdx, i)\
                    )
                    d += 1

                d = 0
                while 'F≤'+str(d) in self.listOfOperators:
                    #parametrized finally
                    operator = 'F≤'+str(d)
                    self.solver.assert_and_track(Implies(self.x[(i, operator)],\
                                                        And([\
                                                            Implies(\
                                                                        self.l[(i,onlyArg)],\
                                                                        And([\
                                                                            self.y[(i, traceIdx, timestep)] ==\
                                                                            Or([self.y[(onlyArg, traceIdx, futureTimestep)] for futureTimestep in tr.futurePos(timestep)[:d+1]])\
                                                                            for timestep in range(tr.lengthOfTrace)\
                                                                            ])\
                                                                        )\
                                                            for onlyArg in range(i)\
                                                            ])\
                                                        ),\
                                                'semantics of parametrized finally≤%d operator for trace %d and depth %d' % (d, traceIdx, i)\
                                                )
                    d += 1
                  
                if 'X' in self.listOfOperators:
                      #next                
                     self.solver.assert_and_track(Implies(self.x[(i, 'X')],\
                                                           And([\
                                                               Implies(\
                                                                         self.l[(i,onlyArg)],\
                                                                         And([\
                                                                              self.y[(i, traceIdx, timestep)] ==\
                                                                              self.y[(onlyArg, traceIdx, tr.nextPos(timestep))]\
                                                                              for timestep in range(tr.lengthOfTrace)\
                                                                              ])\
                                                                          )\
                                                               for onlyArg in range(i)\
                                                               ])\
                                                           ),\
                                                   'semantics of neXt operator for trace %d and depth %d' % (traceIdx, i)\
                                                   )

                d = 0
                while 'U≤'+str(d) in self.listOfOperators:
                    #parametrized until
                    operator = 'U≤'+str(d)
                    self.solver.assert_and_track(Implies(self.x[(i, operator)],\
                        And([ Implies(\
                                        And(\
                                            [self.l[i, leftArg], self.r[i, rightArg]]\
                                            ),\
                                        And([\
                                        self.y[(i, traceIdx, timestep)] ==\
                                        Or([\
                                            And(\
                                                [self.y[(leftArg, traceIdx, futurePos)] for futurePos in tr.futurePos(timestep)[0:qIndex]]+\
                                                [self.y[(rightArg, traceIdx, tr.futurePos(timestep)[qIndex])]]\
                                                )\
                                            for qIndex in range(len(tr.futurePos(timestep))) if qIndex <= d\
                                            ])\
                                        for timestep in range(tr.lengthOfTrace)]\
                                            )\
                                        )\
                            for leftArg in range(i) for rightArg in range(i) ])),\
                        'semantics of parametrized Until≤%d operator for trace %d and depth %d'%(d, traceIdx, i))
                    d += 1
                
                if 'R' in self.listOfOperators:
                    # release
                    self.solver.assert_and_track(Implies(self.x[(i, 'R')],\
                        And([ Implies(\
                                        And(\
                                            [self.l[i, leftArg], self.r[i, rightArg]]\
                                            ),\
                                        And([\
                                            self.y[(i, traceIdx, timestep)] ==\
                                            And([\
                                                Or([\
                                                    self.y[(rightArg, traceIdx, tr.futurePos(timestep)[qIndex])],\
                                                    Or([self.y[(leftArg, traceIdx, futurePos)] for futurePos in tr.futurePos(timestep)[0:qIndex]])\
                                                ])
                                                for qIndex in range(len(tr.futurePos(timestep)))\
                                            ])\
                                            for timestep in range(tr.lengthOfTrace)\
                                        ])\
                                    )\
                            for leftArg in range(i) for rightArg in range(i) ])),\
                        'semantics of release operator for trace %d and depth %d'%(traceIdx, i))

                d = 0
                while 'R≤'+str(d) in self.listOfOperators:
                    # parametrized release
                    operator = 'R≤'+str(d)
                    self.solver.assert_and_track(Implies(self.x[(i, operator)],\
                        And([ Implies(\
                                        And(\
                                            [self.l[i, leftArg], self.r[i, rightArg]]\
                                            ),\
                                        And([\
                                            self.y[(i, traceIdx, timestep)] ==\
                                            And([\
                                                Or([\
                                                    self.y[(rightArg, traceIdx, tr.futurePos(timestep)[qIndex])],\
                                                    Or([self.y[(leftArg, traceIdx, futurePos)] for futurePos in tr.futurePos(timestep)[0:qIndex]])\
                                                ])
                                                for qIndex in range(min(d+1, len(tr.futurePos(timestep))))\
                                            ])\
                                            for timestep in range(tr.lengthOfTrace)\
                                        ])\
                                    )\
                            for leftArg in range(i) for rightArg in range(i) ])),\
                        'semantics of parametrized release≤%d operator for trace %d and depth %d'%(d, traceIdx, i))
                    d += 1

                d = 0
                while 'R>'+str(d) in self.listOfOperators:
                    # parametrized release
                    operator = 'R>'+str(d)
                    self.solver.assert_and_track(Implies(self.x[(i, operator)],\
                        And([ Implies(\
                                        And(\
                                            [self.l[i, leftArg], self.r[i, rightArg]]\
                                            ),\
                                        And([\
                                            self.y[(i, traceIdx, timestep)] ==\
                                            And([\
                                                Or([\
                                                    self.y[(rightArg, traceIdx, tr.futurePos(timestep)[qIndex])],\
                                                    Or([self.y[(leftArg, traceIdx, futurePos)] for futurePos in tr.futurePos(timestep)[0:qIndex]])\
                                                ])
                                                for qIndex in range(d+1, len(tr.futurePos(timestep)))\
                                            ])\
                                            for timestep in range(tr.lengthOfTrace)\
                                        ])\
                                    )\
                            for leftArg in range(i) for rightArg in range(i) ])),\
                        'semantics of parametrized release>%d operator for trace %d and depth %d'%(d, traceIdx, i))
                    d += 1


    def reconstructWholeFormula(self, model):
        return self.reconstructFormula(self.formulaDepth-1, model)   
        
    def reconstructFormula(self, rowId, model):
        def getValue(row, vars):
            tt = [k[1] for k in vars if k[0] == row and model[vars[k]] == True]
            if len(tt) > 1:
                raise Exception("more than one true value")
            else:
                return tt[0]
        operator = getValue(rowId, self.x)
        if operator in self.listOfVariables:
            return Formula('x'+str(operator))
        elif operator in self.unaryOperators:
            leftChild = getValue(rowId, self.l)
            return Formula([operator, self.reconstructFormula(leftChild, model)])
        elif operator in self.binaryOperators:
            leftChild = getValue(rowId, self.l)
            rightChild = getValue(rowId, self.r)
            return Formula([operator, self.reconstructFormula(leftChild,model), self.reconstructFormula(rightChild, model)])
        
    
        
      
