import functools
import io

import json
import textwrap

from django.http import HttpRequest
from django.http import HttpResponseRedirect

import markdown
import profile_images
import sbook.accounts
import sbook.models

from pyoload import *
from quizz import models

from PIL import Image
from pathlib import Path


class Tuple(tuple):
    @property
    def length(self):
        return len(self)


class QuizzUser(sbook.accounts.ModelInder):
    class DoesNotExistError(ValueError):
        pass

    class DoesExistError(ValueError):
        pass

    model: models.QuizzUser = models.QuizzUser

    @classmethod
    def create_from_sbook(cls, sbook):
        try:
            obj = models.QuizzUser(sbookAccount=sbook.model)
            obj.save()
        except Exception as e:
            raise QuizzUser.DoesExistError() from e
        else:
            return cls(obj)

    @functools.cached_property
    @annotate
    def sbook(self: 'QuizzUser') -> sbook.accounts.User:
        return sbook.accounts.User(
            self.model.sbookAccount,
        )

    @functools.cached_property
    @annotate
    def quizzes(self: 'QuizzUser') -> Cast(Tuple[Quizz]):
        return map(Quizz, self.model.quizzes.all())

    @functools.cached_property
    @annotate
    def attempts(self: 'QuizzUser') -> Cast(Tuple[QuizzAttempt]):
        return Tuple(map(QuizzAttempt, self.model.quizz_attempts.all()))

    @functools.cached_property
    def js(self: 'QuizzUser') -> dict[str]:
        return self.sbookAccount.js | {
            "user_id": self.model.id,
        }


class Question:
    @classmethod
    def from_dict(cls, js, i):
        return MCQQuestion(js, i)


class MCQQuestion(Question):
    mode = "mcq"

    def __init__(self, data, id=0):
        self.question = data.get("question")
        self.options = list(data.get("options", {}).items())
        self.answer = data.get("answer")
        self.id = id

    @property
    def js(self):
        return {
            "question": self.question,
            "options": self.options,
        }

    def json(self):
        return json.dumps(self.js)


class Quizz(sbook.accounts.ModelInder):
    class DoesNotExistError(ValueError):
        pass

    class DoesExistError(ValueError):
        pass

    model = models.Quizz

    @functools.cached_property
    @annotate
    def authors(self: 'Quizz') -> Tuple:
        return map(QuizzUser, self.model.authors.all())

    @functools.cached_property
    def short_description(self):
        return textwrap.shorten(self.description, 30)

    @property
    def js(self):
        return {
            "questions": list(map(lambda q: q.id, self.questions)),
            "authors": [author.id for author in self.authors],
            "remarking_status": self.attempts_remark_status,
            "prolog": self.model.prolog,
            "epilog": self.model.epilog,
            "title": self.model.title,
            "num_attempts": self.num_attempts,
            "num_attempts_remarked": self.num_attempts_remarked,
            "num_attempts_unremarked": self.num_attempts_unremarked,
            "id": self.id,
            "stars": self.model.stars,
            "description": self.model.description,
        }

    @functools.cached_property
    def questions(self):
        return Tuple(
            Question.from_dict(data, i)
            for i, data in enumerate(self.data.get("questions") or [])
        )

    @functools.cached_property
    def questions_js(self):
        return tuple(ques.js for ques in self.questions)

    @functools.cached_property
    def attempts(self):
        return tuple(map(QuizzAttempt, self.model.answer_attempts.all()))

    @functools.cached_property
    def num_attempts(self):
        return len(self.attempts)

    @functools.cached_property
    def num_attempts_remarked(self):
        i = 0
        for attempt in self.attempts:
            if attempt.model.remarked:
                i += 1
        return i

    @property
    def num_attempts_unremarked(self):
        return self.num_attempts - self.num_attempts_remarked

    @property
    def attempts_remark_status(self):
        if self.num_attempts == 0 or self.num_attempts_unremarked == 0:
            return 2
        elif self.num_attempts_remarked == 0:
            return 0
        else:
            return 1

    @functools.cached_property
    def on_submit(self):
        return self.data.get(
            "on_submit",
            """Thanks for answering, stydy well!""",
        )


class QuestionAttempt:
    @classmethod
    def from_dict(cls, js, i, a):
        ques = Question.from_dict(js, i)
        return MCQQuestionAttempt(ques, a)

    @classmethod
    def from_question(cls, ques, a):
        print(ques, a)
        return MCQQuestionAttempt(ques, a)


class MCQQuestionAttempt(QuestionAttempt):
    mode = "mcq"

    def __init__(self, question, ans):
        print(question, ans)
        self.answer = ans
        self.question = question


class QuizzAttempt(sbook.accounts.ModelInder):
    class DoesNotExistError(ValueError):
        pass

    class DoesExistError(ValueError):
        pass

    model = models.QuizzAttempt

    @classmethod
    def create(cls, author, quizz, answers):
        model = models.QuizzAttempt(
            answers=answers,
            author=author.model,
            quizz=quizz.model,
        )
        model.save()
        return cls(model)

    @functools.cached_property
    @annotate
    def author(self: 'QuizzAttempt') -> Cast(QuizzUser):
        return self.model.author

    @functools.cached_property
    def js(self: 'QuizzAttempt'):
        return {
            "id": self.model.id,
            "quizz": self.quizz.id,
            "author": self.author.id,
            "answers": self.model.answers,
            "remarks": self.model.remarks,
            "score": self.model.score,
            "remarked": self.model.remarked,
        }

    @functools.cached_property
    @annotate
    def quizz(self: 'QuizzAttempt') -> Quizz:
        return Quizz(self.model.quizz)

    @functools.cached_property
    @annotate
    def answers(self: 'QuizzAttempt') -> Tuple[QuestionAttempt]:
        ret = tuple(
            QuestionAttempt.from_question(self.quizz.questions[i], a)
            for i, a in enumerate(self.model.answers)
        )
        return ret


def check_login(func, redirect=True):
    if isinstance(func, bool):
        return functools.partial(
            check_login,
            redirect=func,
        )

    @functools.wraps(func)
    def wrapper(*args, **kw):
        req = args[0]
        if not isinstance(req, HttpRequest):
            req = args[1]
        if "user-id" in req.session:
            try:
                user = QuizzUser.from_id(req.session.get("user-id", -1))
            except QuizzUserDoesNotExistError:
                if not redirect:
                    return func(user=None, *args, **kw)
                return HttpResponseRedirect("/signin/")
            except QuizzUserDoesNotExistError:
                user = QuizzUser.create_from_sbook(
                    sbook.accounts.User.from_id(req.session.get("user-id")),
                )
            return func(user=user, *args, **kw)
        else:
            if not redirect:
                return func(user=None, *args, **kw)
            return HttpResponseRedirect("/signin/")

    return wrapper
