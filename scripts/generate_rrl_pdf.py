#!/usr/bin/env python3
"""Generate docs/thesis/rrl.pdf — RRL with 5 titled entries per category and APA references."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "thesis" / "rrl.pdf"

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=15, spaceAfter=6, alignment=TA_CENTER)
SUBTITLE = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=11, spaceAfter=14, alignment=TA_CENTER)
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=13, spaceBefore=10, spaceAfter=8, textColor=colors.HexColor("#1e3a5f"))
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#2a4d80"))
BODY = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10.5, leading=16, alignment=TA_JUSTIFY, firstLineIndent=0.5 * cm, spaceAfter=10)
REF = ParagraphStyle("Ref", parent=styles["Normal"], fontSize=10, leading=14, alignment=TA_LEFT, leftIndent=0.75 * cm, firstLineIndent=-0.75 * cm, spaceAfter=8)

# Each section: (section title, [ (entry title, [paragraph, ...]), ... ])
SECTIONS = [
    (
        "Foreign Literature",
        [
            (
                "Artificial Intelligence and Smart Technologies in Education: An International Perspective",
                [
                    "The OECD (2021) Digital Education Outlook provides a comprehensive international examination of how smart technologies, particularly artificial intelligence (AI), learning analytics, and robotics, are transforming education systems. The report documents that personalized and adaptive learning has become a mature field, with intelligent systems capable of diagnosing student needs and delivering tailored content and feedback. It also explores how these technologies support students with special learning needs and how blockchain is reshaping credentialing and learner records.",
                    "Beyond describing technological possibilities, the OECD report emphasizes that digital education must be understood as a complex interplay of technology, pedagogy, and governance. It cautions that equity gaps, data privacy concerns, and the need for human oversight are critical conditions for the responsible deployment of AI in classrooms. The report asserts that the success of digital transformation depends less on the sophistication of the tools themselves and more on how well they are aligned with sound learning principles and institutional readiness.",
                    "Synthesis. This international literature supports the current study by establishing a policy-validated framework for integrating AI into education. It provides the justification for ExamiQ's AI-assisted tutor and dynamic feedback features, affirming that such technologies are legitimate when anchored on pedagogy, learner-centeredness, and clear human oversight.",
                ],
            ),
            (
                "Global Assessment of Learning and Equity: Lessons from the PISA 2022 Results",
                [
                    "The OECD (2023) PISA 2022 Results provide a global snapshot of the mathematics, reading, and science performance of 15-year-old students across participating economies. The report reveals a record decline in mathematics performance between 2018 and 2022, with an average drop of fifteen points across OECD countries, underscoring the disruptive impact of the pandemic on foundational learning. It also documents wide disparities in learning opportunities among students from different socioeconomic backgrounds.",
                    "Beyond raw scores, the report draws attention to the affective dimensions of learning, particularly students' confidence and self-efficacy. It argues that mathematics literacy is essential for future learning and employment, and that sustained improvement requires not only content mastery but also the development of learners' belief in their own capabilities. These findings position mathematics confidence as a lever that educators and technology designers can intentionally cultivate.",
                    "Synthesis. This foreign literature supports the current study by supplying international evidence of declining mathematics performance coupled with weak learner confidence. It reinforces ExamiQ's design premise that confidence-based review sessions, which combine calibrated self-assessment with structured practice, can address both academic performance and the self-belief of college students in mathematics.",
                ],
            ),
            (
                "The State of the Art in Artificial Intelligence for Education",
                [
                    "Holmes and Tuomi (2022) provide a state-of-the-art review of artificial intelligence in education, clarifying common misconceptions about how AI learns and operates. They develop a typology of AIED systems that distinguishes learning analytics, intelligent tutoring systems, and adaptive learning environments, and they explain how these systems are grounded in different interpretations of what education is and should be.",
                    "The authors argue that the educational value of AI depends on the pedagogical assumptions embedded in its design. They stress that AI should augment, not replace, the human elements of teaching and learning, and they caution that inflated expectations, narrow views of education, and a lack of rigorous evaluation can undermine the effective use of these technologies. Their typology offers researchers a vocabulary for describing exactly how and why an AI tool is deployed in a learning context.",
                    "Synthesis. This foreign literature supports the current study by offering a conceptual framework for classifying AI-based educational technologies. It guides ExamiQ's design decision to position its AI tutor as a pedagogical support for self-regulated mathematics review rather than as a substitute for the learner's own metacognitive engagement, ensuring that the system's intelligent features serve clearly defined learning purposes.",
                ],
            ),
            (
                "The Effort Monitoring and Regulation Framework in Self-Regulated Learning",
                [
                    "de Bruin, Roelle, Carpenter, and Baars (2020) introduce the effort monitoring and regulation (EMR) framework, which integrates cognitive load theory and self-regulated learning theory. The framework argues that learners' accurate monitoring of their mental effort is a neglected but essential component of self-regulated learning, and it positions monitoring and regulation as processes operating at a metacognitive level while learners engage with learning tasks.",
                    "The authors demonstrate that prompting students to judge their own learning, through methods such as confidence judgments and self-assessments, can improve monitoring accuracy and, consequently, learning outcomes. They identify three research directions: how students monitor effort, how they regulate effort, and how cognitive load can be optimized during self-regulated learning tasks, both during and after the primary task.",
                    "Synthesis. This foreign literature directly underpins the current study's confidence-based test flow. It provides the theoretical basis for ExamiQ's use of confidence ratings to sharpen students' calibration, showing that prompting learners to evaluate their answers promotes accurate self-monitoring and more effective self-regulated review of mathematics concepts.",
                ],
            ),
            (
                "Motivation, Self-Efficacy, and Social Cognitive Theory",
                [
                    "Schunk and DiBenedetto (2020) review motivation from the perspective of Bandura's social cognitive theory, explaining that self-efficacy, goals, outcome expectations, and self-regulation interact to influence learners' effort, persistence, and achievement. They describe how motivational processes operate as personal influences within a framework of reciprocal interactions between behavior, environment, and personal factors.",
                    "The authors emphasize that self-efficacy is both a product and a determinant of learning experiences, and that feedback, mastery experiences, and social modeling shape students' beliefs about their capabilities. They note that accurate performance feedback is one of the strongest sources of self-efficacy in academic settings, and they highlight the increasing relevance of these constructs to technology-mediated learning.",
                    "Synthesis. This literature supports the current study by establishing the theoretical link between self-efficacy and self-regulated learning. It provides the rationale for ExamiQ's progress dashboards and cumulative accuracy feedback, which are designed to strengthen students' mathematics self-efficacy through observable evidence of mastery and improvement across review sessions.",
                ],
            ),
        ],
    ),
    (
        "Local Literature",
        [
            (
                "Flexible Learning Guidelines in Philippine Higher Education",
                [
                    "The Commission on Higher Education (2020), through Memorandum Order No. 04, series of 2020, issued the guidelines on the implementation of flexible learning in Philippine higher education institutions. The order defines flexible learning as a pedagogical approach allowing flexibility of time, place, pace, and audience, and it directs institutions to adopt delivery modes that are responsive to learners' unique circumstances.",
                    "The policy mandates the use of digital and non-digital technologies and covers face-to-face, out-of-classroom, and blended modes of delivery, ensuring the continuity of inclusive and accessible education even during national emergencies. It further requires institutions to strengthen their learning management systems and faculty capabilities to support flexible modalities.",
                    "Synthesis. This local literature supports the current study by providing the regulatory basis for a web-based, self-paced review platform in Philippine higher education. It positions ExamiQ as a flexible and accessible learning tool that aligns with the national flexible learning guidelines, allowing college students to conduct self-regulated mathematics review anytime and anywhere.",
                ],
            ),
            (
                "The Basic Education Learning Continuity Plan Amid the Pandemic",
                [
                    "The Department of Education (2020), through Order No. 012, series of 2020, adopted the Basic Education Learning Continuity Plan (BE-LCP) to ensure the continuation of learning during the COVID-19 public health emergency. The order streamlined the K to 12 Curriculum into the Most Essential Learning Competencies and allowed schools to deliver instruction through multiple learning modalities and platforms.",
                    "The BE-LCP recognized that learners must take greater responsibility for their own progress when direct classroom instruction is limited, making self-directed learning a central feature of distance education. It also established monitoring and evaluation frameworks to assess how learning delivery adapted to local conditions and constraints.",
                    "Synthesis. While directed at basic education, this local literature supports the current study by normalizing self-directed, technology-mediated learning in the Philippine context. It reinforces ExamiQ's emphasis on student-driven, self-regulated review, which mirrors the continuity-plan approach of flexible and remote learning adopted nationwide during educational disruptions.",
                ],
            ),
            (
                "The Basic Education Development Plan 2030: The National Roadmap",
                [
                    "The Department of Education (2022), through Order No. 024, series of 2022, adopted the Basic Education Development Plan 2030, the country's first long-term roadmap for basic education. The plan covers formal education from kindergarten through senior high school as well as nonformal education, and it was developed through a highly participatory process aligned with the Sustainable Development Goals.",
                    "The BEDP 2030 prioritizes the immediate recovery of learning, the improvement of reading and numeracy skills, and the introduction of innovations in education technology. It explicitly establishes the National Mathematics Program to strengthen mathematics learning, treating numeracy proficiency as a foundation for lifelong development.",
                    "Synthesis. This local literature supports the current study by affirming the national priority on mathematics improvement and technology-enabled instruction. It provides policy alignment for ExamiQ's objective of raising mathematics performance among college students, positioning the system as a complement to the country's long-term mathematics agenda.",
                ],
            ),
            (
                "The MATATAG Curriculum: Reforming Basic Education",
                [
                    "The Department of Education (2024), through Order No. 010, series of 2024, issued the policy guidelines for the implementation of the MATATAG Curriculum, a decongested K to 10 curriculum designed to develop learners with strong foundational literacies, including mathematics. The curriculum emphasizes critical thinking, problem solving, and the judicious use of technology to support learning.",
                    "The policy makes formative assessment a core instructional practice, directing teachers to use assessment tools not only for grading but for monitoring learning gains and guiding subsequent instruction. It also provides guidance to instructional leaders in supervising delivery and providing technical assistance to teachers and schools.",
                    "Synthesis. This local literature supports the current study by reflecting the national shift toward mastery-oriented, technology-supported mathematics learning. It aligns with ExamiQ's confidence-based formative review and mistake-tracking features, which embody the MATATAG emphasis on deeper understanding, continuous assessment, and the purposeful integration of technology in learning.",
                ],
            ),
            (
                "Miseducation: The EDCOM II Year One Report",
                [
                    "The Second Congressional Commission on Education (2024) released its Year One Report, Miseducation: The Failed System of Philippine Education, documenting persistent learning poverty, resource gaps, and governance weaknesses across the education sector. The report highlights fragmented coordination among DepEd, CHED, and TESDA, and it identifies mathematics as one of the areas where Filipino learners lag furthest behind international benchmarks.",
                    "Drawing on extensive research, consultations, and site visits, the commission calls for comprehensive reforms in curriculum, instruction, and assessment, and it advocates the use of technology and evidence-based practice to address learning losses and improve instructional quality across basic and higher education.",
                    "Synthesis. This local literature supports the current study by diagnosing the systemic challenges that motivate educational technology interventions in the Philippines. It frames ExamiQ as a targeted, evidence-driven response to the mathematics learning gaps identified in the national education landscape, contributing to the country's reform agenda.",
                ],
            ),
        ],
    ),
    (
        "Local Studies",
        [
            (
                "E-Learning Readiness of Filipino Higher Education Students",
                [
                    "Reyes, Grajo, Comia, Talento, Ebal, and Mendoza (2021) assessed the e-learning readiness of Filipino higher education students during the pandemic using Rasch analysis of the Online Learning Readiness Scale. Their findings indicated that students were generally ready in terms of computer and internet self-efficacy, but less ready in terms of learner control and self-directed learning.",
                    "The study further found that gender significantly differentiated readiness under learner control and self-directed learning, while program classification produced differences in computer and internet self-efficacy and online communication self-efficacy. The authors concluded that readiness for online learning is not uniform, and that self-directed learning is among the weakest dimensions among Filipino college students.",
                    "Synthesis. This local study supports the current study by identifying a readiness gap in self-directed learning among Filipino college students. It validates the design of ExamiQ's self-regulated review workflow, which includes session planning, goal setting, progress tracking, and confidence calibration, as an intervention precisely aimed at the weakest dimension of student readiness.",
                ],
            ),
            (
                "Self-Regulated Learning and Mathematics Performance Among Grade 10 Students",
                [
                    "Balones, Basañez, Decorina, Rafanan, Napitan, and Legaspino (2024) conducted a descriptive-correlational study of 69 Grade 10 students to examine the influence of self-regulated learning on academic performance in mathematics. Using an adapted survey and a validated researcher-made test, they found that self-regulated learning was evident in most instances, while mathematics performance was generally satisfactory but did not consistently meet expectations.",
                    "Contrary to expectations, the study revealed no significant relationship between self-regulated learning and academic performance in mathematics, and no specific domain of self-regulated learning significantly influenced performance. The authors recommended exploring additional variables and instructional interventions that could translate self-regulation into measurable learning gains.",
                    "Synthesis. This local study supports the current study by highlighting that the mere presence of self-regulatory skills does not guarantee achievement. It motivates ExamiQ's combination of confidence-based flow, dynamic feedback, and mistake tracking, which are designed to deliberately scaffold self-regulation so that it converts into tangible mathematics improvement.",
                ],
            ),
            (
                "AI-Powered Mathematics Tutors and Calculus Learning",
                [
                    "Alvarez, Cortez, and Alberto (2024) conducted an experimental study at a state university in the Philippines to evaluate the effectiveness of AI-powered mathematics tutors, MathGPT and Flexi 2.0, among pre-service mathematics educators taking Calculus I. Using a pre-test and post-test design with validated instruments, they found that students using the AI tutors showed significant improvements in problem solving and personalized learning compared with the control group.",
                    "The study also raised important concerns about potential over-reliance on AI, underscoring the need for strict guidance and monitoring so that learners actively engage with solutions rather than passively receiving AI-generated responses. The authors recommended activities that require students to critically evaluate AI outputs, as well as training for both students and faculty.",
                    "Synthesis. This local study directly supports the current study by providing Philippine evidence that AI-assisted mathematics tutoring improves performance when properly supervised. It validates ExamiQ's integration of an AI tutor as a personalized support layer, while reminding the design team to frame AI feedback as a stimulus for critical thinking within self-regulated review.",
                ],
            ),
            (
                "Self-Efficacy and Self-Regulation in Mathematics Concept Processing",
                [
                    "Rivera and Canoy (2025) examined the relationship between self-efficacy and self-regulation in the cognitive processing and mastery of mathematical concepts among secondary public school students in Trece Martires City. Using a quantitative descriptive-correlational design with 60 students, they found generally positive self-efficacy and strong self-regulation, with a small but statistically significant positive correlation between the two constructs.",
                    "The study concluded that students' belief in their mathematical abilities is meaningfully associated with how well they manage and control their learning behaviors, such as goal setting, self-monitoring, and persistence. The authors recommended targeted interventions that concurrently develop self-efficacy and self-regulatory strategies, including strategy training, teacher support, and reflective learning practices.",
                    "Synthesis. This local study supports the current study by establishing the empirical connection between self-efficacy and self-regulation in the Philippine mathematics classroom. It reinforces ExamiQ's use of confidence ratings and calibration feedback as a mechanism to strengthen both constructs among college students during exam review.",
                ],
            ),
            (
                "Self-Regulated Learning and Mathematical Modeling in Technology-Enhanced Classrooms",
                [
                    "Paguyo (2026) investigated the relationship between self-regulated learning and mathematical modeling competence among secondary school students in technology-enhanced classrooms at Isabela National High School. Using a descriptive-correlational design, the study measured self-regulated learning in terms of goal setting and planning, self-monitoring and strategy use, and self-reflection and adjustment.",
                    "The findings revealed high levels of both self-regulated learning and mathematical modeling competence, a significant positive relationship between the two variables, and self-monitoring and strategy use as the strongest predictors of modeling competence. The study concluded that strengthening self-regulatory capacities in technology-enhanced mathematics classrooms contributes to improved performance in modeling-oriented tasks.",
                    "Synthesis. This recent local study supports the current study by demonstrating that self-monitoring and strategy use are the most salient dimensions of self-regulated learning in mathematics. It provides empirical justification for ExamiQ's emphasis on confidence-based monitoring and reflective feedback within a technology-enhanced review environment for college students.",
                ],
            ),
        ],
    ),
    (
        "Foreign Studies",
        [
            (
                "Artificial Intelligence in Higher Education: The State of the Field",
                [
                    "Crompton and Burke (2023) systematically reviewed 138 articles published between 2016 and 2022 to examine the use of artificial intelligence in higher education. Using PRISMA principles, they found that research in this area has grown rapidly, particularly in 2021 and 2022, with undergraduate students as the most studied population and language learning as the most common subject domain.",
                    "The review identified five dominant uses of AI in higher education: assessment and evaluation, prediction, AI assistants, intelligent tutoring systems, and managing student learning. It also highlighted gaps in the literature, including the need for studies of new tools such as generative AI, and it called attention to the shift in research leadership toward departments of education.",
                    "Synthesis. This foreign study supports the current study by mapping the established applications of AI in higher education and confirming that AI-based tutoring and assessment are among the most mature uses of the technology. It validates ExamiQ's integration of an AI tutor and automated feedback as evidence-based features of a college-level mathematics review platform.",
                ],
            ),
            (
                "Intelligent Tutoring System Usage and Learning Gains in Mathematics",
                [
                    "Schaaf, Rolfes, Nagy, and Heinze (2026) conducted a longitudinal study of 940 students in 55 classes to examine whether the frequency of intelligent tutoring system (ITS) use influenced mathematics learning gains. Using multilevel analysis with a pre-post test design, they found that the frequency of ITS usage had no significant effect on learning gains once prior performance and other covariates were controlled.",
                    "The authors concluded that simply using an ITS does not automatically lead to better learning outcomes, and they stressed that the quality and focus of interaction with the technology matter more than its quantity. They recommended that future research identify the conditions and instructional practices that contribute to effective ITS use.",
                    "Synthesis. This foreign study informs the current study by cautioning that exposure to intelligent tutoring alone is insufficient. It underscores the need for ExamiQ's deliberate design, including confidence ratings, mistake tracking, and reflective feedback, so that its review sessions are genuinely productive rather than merely frequent.",
                ],
            ),
            (
                "Calibration Discrepancy and Metacognitive Strategy Use in Computer-Based Learning",
                [
                    "Lee and Bosch (2025) analyzed data from 210 college students using a computer-based learning environment to examine how calibration discrepancy relates to metacognitive strategy use. They found that students who overestimated their pretest performance engaged in fewer metacognitive strategies, particularly preparatory actions before quizzes, and that retrospective judgments predicted subsequent strategy engagement more strongly than actual scores.",
                    "The study also found that students who repeatedly engaged in quiz-taking tended to adjust their judgments more conservatively. The authors advocate for early, proactive calibration support tools that go beyond presenting information, offering guidance on interpreting feedback and implementing strategies to better align students' judgments with their actual performance.",
                    "Synthesis. This foreign study directly validates the current study's confidence-rating mechanism. It provides empirical evidence that helping students calibrate their judgments can increase their use of metacognitive strategies, which is precisely the outcome ExamiQ aims to foster through its confidence-based review sessions and calibration summaries.",
                ],
            ),
            (
                "Perceived Self-Efficacy as a Moderator of Self-Regulation in Mathematics Problem Solving",
                [
                    "Landa, Berciano, and Marbán (2025) constructed a structural equation model using data from 402 first-year university students to test whether perceived self-efficacy moderates self-regulation in mathematical problem solving. Their results confirmed that the perception of self-efficacy functions as a moderator of the level of self-regulation, meaning that students' confidence in their mathematical abilities shapes how effectively they plan, monitor, and reflect.",
                    "The study established that self-efficacy beliefs are not merely an outcome of learning but an active influence on the problem-solving process itself, affecting students' attitudes, behaviors, and management of learning resources. Students with higher self-efficacy tended to set more challenging goals and demonstrate greater perseverance in seeking solutions.",
                    "Synthesis. This foreign study supports the current study by providing quantitative evidence that self-efficacy moderates self-regulation in mathematics among university students. It reinforces ExamiQ's aim to cultivate confidence through calibrated feedback so that college students regulate their mathematics review more effectively.",
                ],
            ),
            (
                "AI-Driven Intelligent Tutoring Systems and Learning Performance",
                [
                    "Létourneau, Deslandes Martineau, Charland, Karran, Boasen, and Léger (2025) systematically reviewed 28 studies involving 4,597 students to evaluate the effects of AI-driven intelligent tutoring systems on learning and performance in K-12 education. Their findings indicated generally positive effects of intelligent tutoring systems, although the advantages were mitigated when compared with non-intelligent tutoring systems.",
                    "The review emphasized that intelligent tutoring systems are most effective when combined with teacher-led guidance and when they incorporate self-regulation features such as skill tracking and reflection prompts. The authors called for longer interventions and more diverse samples, noting that self-assessment features and mastery-based progress help students take greater ownership of their learning.",
                    "Synthesis. This foreign study supports the current study by providing synthesized evidence on the effectiveness of intelligent tutoring systems. It informs the design of ExamiQ's AI-assisted feedback, confirming that the system should integrate self-regulation features, such as confidence prompts and progress summaries, to ensure its contribution to mathematics review exceeds what conventional question drills offer.",
                ],
            ),
        ],
    ),
]

REFERENCES = [
    "Alvarez, J. I., Cortez, A. O., & Alberto, M. Z. (2024). Personalized learning in action: Utilizing AI-powered tutors to bridge the gap in mathematics. International Journal of Research Studies in Education, 13(8), 15–25. https://doi.org/10.5861/ijrse.2024.24074",
    "Balones, J. M. B., Basañez, R. J. R., Decorina, L. S., Rafanan, K. J. M., Napitan, S. A. A., & Legaspino, D. M. (2024). Influence of self-regulated learning on the academic performance in mathematics. EPRA International Journal of Multidisciplinary Research, 10(8). https://doi.org/10.36713/epra18051",
    "Commission on Higher Education. (2020). Guidelines on the implementation of flexible learning (CHED Memorandum Order No. 04, s. 2020). https://ched.gov.ph/2020-ched-memorandum-orders/",
    "Crompton, H., & Burke, D. (2023). Artificial intelligence in higher education: The state of the field. International Journal of Educational Technology in Higher Education, 20, Article 22. https://doi.org/10.1186/s41239-023-00392-8",
    "de Bruin, A. B. H., Roelle, J., Carpenter, S. K., & Baars, M. (2020). Synthesizing cognitive load and self-regulation theory: A theoretical framework and research agenda. Educational Psychology Review, 32(4), 903–915. https://doi.org/10.1007/s10648-020-09576-4",
    "Department of Education. (2020). Adoption of the Basic Education Learning Continuity Plan for School Year 2020-2021 in light of the COVID-19 public health emergency (DepEd Order No. 012, s. 2020). https://deped.gov.ph/wp-content/uploads/2020/06/DO_s2020_012.pdf",
    "Department of Education. (2022). Adoption of the Basic Education Development Plan 2030 (DepEd Order No. 024, s. 2022). https://www.deped.gov.ph/wp-content/uploads/2022/05/DO_s2022_024.pdf",
    "Department of Education. (2024). Policy guidelines on the implementation of the MATATAG curriculum (DepEd Order No. 010, s. 2024). https://www.deped.gov.ph/wp-content/uploads/DO_s2024_010.pdf",
    "Holmes, W., & Tuomi, I. (2022). State of the art and practice in AI in education. European Journal of Education, 57(4), 542–570. https://doi.org/10.1111/ejed.12533",
    "Landa, J., Berciano, A., & Marbán, J. M. (2025). Moderating effect of perceived self-efficacy on university students' self-regulation in mathematics problem solving. International Journal of Science and Mathematics Education, 23, 3815–3839. https://doi.org/10.1007/s10763-025-10597-0",
    "Lee, H., & Bosch, N. (2025). Calibration discrepancy predicts students' subsequent metacognitive strategy use in computer-based learning environments. International Journal of Artificial Intelligence in Education, 35(6), 3746–3779. https://doi.org/10.1007/s40593-025-00514-5",
    "Létourneau, A., Deslandes Martineau, M., Charland, P., Karran, J. A., Boasen, J., & Léger, P. M. (2025). A systematic review of AI-driven intelligent tutoring systems (ITS) in K-12 education. npj Science of Learning, 10, Article 29. https://doi.org/10.1038/s41539-025-00320-7",
    "OECD. (2021). OECD digital education outlook 2021: Pushing the frontiers with artificial intelligence, blockchain and robots. OECD Publishing. https://doi.org/10.1787/589b283f-en",
    "OECD. (2023). PISA 2022 results (Volume I): The state of learning and equity in education. OECD Publishing. https://doi.org/10.1787/53f23881-en",
    "Paguyo, E. B. (2026). Self-regulated learning and mathematical modeling competence among secondary school students in technology-enhanced classrooms. International Journal of Education, Research, and Innovation Perspectives, 2(4), 1248–1265. https://doi.org/10.5281/zenodo.19723925",
    "Reyes, J. R. S., Grajo, J. D. L., Comia, L. N., Talento, M. S. D. P., Ebal, L. P. A., & Mendoza, J. J. O. (2021). Assessment of Filipino higher education students' readiness for e-learning during a pandemic: A Rasch technique application. Philippine Journal of Science, 150(3), 1007–1018. https://doi.org/10.56899/150.03.34",
    "Rivera, M., & Canoy, O. (2025). Self-efficacy and self-regulation in the cognitive processing and mastery of mathematical concepts among students in selected secondary public schools of Trece Martires City. Psychology and Education: A Multidisciplinary Journal, 45(9), 1161–1169. https://doi.org/10.70838/pemj.450908",
    "Schaaf, J., Rolfes, T., Nagy, G., & Heinze, A. (2026). The effect of the frequency of use of an intelligent tutoring system on learning gains in mathematics secondary education. Frontiers in Education, 10, Article 1738655. https://doi.org/10.3389/feduc.2025.1738655",
    "Schunk, D. H., & DiBenedetto, M. K. (2020). Motivation and social cognitive theory. Contemporary Educational Psychology, 60, Article 101832. https://doi.org/10.1016/j.cedpsych.2019.101832",
    "Second Congressional Commission on Education. (2024). Miseducation: The failed system of Philippine education, EDCOM II year one report. https://edcom2.gov.ph/media/2024/02/EDCOM-II-Year-One-Report-PDF-022924.pdf",
]


def build_story():
    story = []
    story.append(Paragraph("EXAMIQ", TITLE))
    story.append(Paragraph("A Self-Regulated Mathematics Exam Review System for College Students", SUBTITLE))
    story.append(Paragraph("Review of Related Literature", TITLE))
    story.append(Spacer(1, 0.4 * cm))

    for section_index, (title, entries) in enumerate(SECTIONS, start=1):
        story.append(PageBreak())
        story.append(Paragraph(f"{section_index}. {title}", H1))
        for entry_index, (entry_title, paragraphs) in enumerate(entries, start=1):
            story.append(Paragraph(f"{section_index}.{entry_index} {entry_title}", H2))
            for body in paragraphs:
                story.append(Paragraph(body, BODY))

    story.append(PageBreak())
    story.append(Paragraph("References", H1))
    for ref in REFERENCES:
        story.append(Paragraph(ref, REF))

    return story


def main():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="ExamiQ Review of Related Literature",
        author="ExamiQ",
    )
    doc.build(build_story())
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
