from django.test import SimpleTestCase
from .services import _evidence_score


class EvidenceScoringTests(SimpleTestCase):
    def test_all_evidence_can_earn_full_thirty_points(self):
        score, details = _evidence_score({"skills": "Python", "experience": "Internship: built a project"}, "", {})
        self.assertEqual(score, 30)
        self.assertEqual(details["internship"]["earned"], 15)

    def test_recruiter_ranking_changes_evidence_points(self):
        data = {"experience": "Internship"}
        internship_first, _ = _evidence_score(data, "", {"Internship": 50, "Projects": 33.3333, "Self-proclaimed skills": 16.6667})
        projects_first, _ = _evidence_score(data, "", {"Projects": 50, "Internship": 33.3333, "Self-proclaimed skills": 16.6667})
        self.assertEqual(internship_first, 15)
        self.assertEqual(projects_first, 10)
