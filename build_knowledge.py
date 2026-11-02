"""
build_knowledge.py - Generates the complete, high-coverage knowledge.json for SIT Tumkur.
Contains a broad reviewed SIT knowledge base with extensive keywords, phonetic variants, student question templates,
and verified authentic college facts.
"""

import json
import os

TOPICS = [
    {
        "id": "identity",
        "title": "Robot Identity",
        "category": "general",
        "keywords": [
            "who are you", "what is your name", "your name", "tell me about yourself",
            "what are you", "who made you", "are you a robot", "humanoid",
            "assistant", "robot", "sit bot", "campus bot", "sit robot", "who r u",
            "introduce yourself", "identity", "robot name"
        ],
        "answer": (
            "I am the autonomous humanoid campus assistant of Siddaganga Institute of Technology, "
            "Tumakuru. I run completely offline to answer all your questions about our college, "
            "admissions, placements, departments, hostels, and facilities."
        )
    },
    {
        "id": "about_sit",
        "title": "About SIT Tumkur",
        "category": "overview",
        "keywords": [
            "about sit", "about siddaganga", "what is sit", "what is safety",
            "what is the safety", "tell me about safety", "siddaganga institute of technology", "sit tumkur",
            "history of sit", "when was sit started", "when was sit established",
            "when was sit founded", "college history", "autonomous", "accreditation",
            "naac", "aicte", "vtu affiliated", "campus area", "ranking", "nirf", "grade",
            "about college", "tell me about sit", "overview of sit"
        ],
        "answer": (
            "Siddaganga Institute of Technology (SIT), Tumakuru was established in 1963 by the "
            "Sree Siddaganga Education Society. It is an autonomous institution affiliated to "
            "Visvesvaraya Technological University (VTU), Belagavi, approved by AICTE, and "
            "accredited by NAAC with an 'A++' Grade."
        )
    },
    {
        "id": "founder_swamiji",
        "title": "Founder - Dr. Sree Sree Shivakumara Swamigalu",
        "category": "leadership",
        "keywords": [
            "founder", "swamiji", "sivakumara", "shivakumara", "walking god", "trividha dasohi",
            "kayaka yogi", "who founded sit", "who founded siddaganga", "who founded siddaganga mutt",
            "siddaganga math", "siddaganga mutt", "dr sree sree shivakumara swamigalu",
            "padma bhushan", "karnataka ratna", "centenarian seer", "who started sit"
        ],
        "answer": (
            "SIT was founded by His Holiness Padma Bhushan Dr. Sree Sree Shivakumara Swamigalu, "
            "revered as the 'Walking God' and 'Trividha Dasohi' for providing free food, shelter, "
            "and education to tens of thousands of children at Sree Siddaganga Math."
        )
    },
    {
        "id": "president_swamiji",
        "title": "President - Sree Sree Siddalinga Swamiji",
        "category": "leadership",
        "keywords": [
            "president", "siddalinga", "siddalinga swamiji", "current swamiji", "head of math",
            "present president", "sree sree siddalinga swamigalu", "education society president",
            "who is the president"
        ],
        "answer": (
            "The Sree Siddaganga Education Society is currently guided and presided over by "
            "His Holiness Sree Sree Siddalinga Swamigalu, who continues the humanitarian and "
            "educational vision of the Math."
        )
    },
    {
        "id": "principal_sit",
        "title": "Principal of SIT",
        "category": "leadership",
        "keywords": [
            "principal", "principle", "who is the principal", "principal of sit",
            "who is principal of sit", "principal of sit tumkur", "who is the principal of sit",
            "principal of sit is", "principle of sit is", "principal of a set", "principle of a set",
            "principal of sad", "principle of sad", "tell me about our principal",
            "who is our principal", "principal of our college", "principle of our college",
            "sit principal", "head of the college", "principal name", "dinesh",
            "dr s v dinesh", "prof dinesh", "dinesh sir", "current principal",
            "headmaster", "college head", "who is the principle", "who is principal"
        ],
        "answer": (
            "The Principal of Siddaganga Institute of Technology is Dr. S. V. Dinesh. "
            "His office is situated in the main administrative block."
        )
    },
    {
        "id": "leadership_management",
        "title": "Director and CEO",
        "category": "leadership",
        "keywords": [
            "director", "ceo", "channabasappa", "dr m n channabasappa", "shivakumaraiah",
            "joint secretary", "who is the director", "who is the ceo", "college leadership",
            "who manages sit", "sit management team"
        ],
        "answer": (
            "Dr. M. N. Channabasappa serves as the Director of SIT, and Dr. Shivakumaraiah serves "
            "as the Chief Executive Officer (CEO) and Joint Secretary of Sree Siddaganga Education Society."
        )
    },
    {
        "id": "location_address",
        "title": "Location and Address",
        "category": "navigation",
        "keywords": [
            "where is sit", "location of sit", "address of sit", "where is the college located",
            "tumkur address", "pincode", "b h road", "tumakuru location", "sit address",
            "which district", "landmark of sit"
        ],
        "answer": (
            "SIT is located on B.H. Road (Bengaluru-Honnavar Road, NH 206) in Tumakuru, "
            "Karnataka, PIN code 572 103, approximately 70 kilometers northwest of Bengaluru."
        )
    },
    {
        "id": "how_to_reach",
        "title": "How to Reach SIT",
        "category": "navigation",
        "keywords": [
            "how to reach", "how to go to sit", "route to sit", "railway station to sit",
            "bus stand to sit", "distance from bangalore", "nearest airport", "directions to sit",
            "travel to sit", "how to visit sit", "tumkur railway station"
        ],
        "answer": (
            "SIT is easily accessible: it is just 5 kilometers from both the Tumakuru Railway Station "
            "and KSRTC Main Bus Stand (about 10 to 15 minutes by auto or local bus). The nearest airport "
            "is Kempegowda International Airport Bengaluru, approximately 85 kilometers away."
        )
    },
    {
        "id": "contact_details",
        "title": "Contact Information and Website",
        "category": "navigation",
        "keywords": [
            "contact", "phone number", "email of sit", "office number", "website of sit",
            "enquiry number", "how to contact sit", "principal email", "reception number", "helpline"
        ],
        "answer": (
            "You can contact SIT by telephone at 0816-2214000 or 0816-2282696. "
            "The official email is principal@sit.ac.in and the college website is sit.ac.in."
        )
    },
    {
        "id": "admissions_kcet_comedk",
        "title": "Engineering Admissions (KCET & COMEDK)",
        "category": "admissions",
        "keywords": [
            "admission", "admissions", "kcet", "kcet code", "comedk", "comedk code",
            "sit kcet code", "sit comedk code", "e016", "e125", "college code for sit",
            "how to get admission", "eligibility for engineering", "joining sit",
            "b tech admission", "b e admission", "engineering admission", "cutoff rank",
            "cut off rank", "kcet cutoff rank"
        ],
        "answer": (
            "Undergraduate engineering admissions include Karnataka CET (KEA), COMEDK, and other applicable "
            "categories. Check the current admission notice for eligibility, seat availability, and deadlines."
        )
    },
    {
        "id": "admissions_management_quota",
        "title": "Management Quota Admissions",
        "category": "admissions",
        "keywords": [
            "management quota", "management seat", "direct admission", "management quota seat",
            "management admission", "direct seat", "how to get management seat", "management fees"
        ],
        "answer": (
            "For Management Quota admissions, applicants should contact the college administrative office "
            "directly or visit the admissions section on sit.ac.in. Seats are allotted based on merit in "
            "10+2 examinations and availability in the respective engineering branch."
        )
    },
    {
        "id": "admissions_pg_mba_mca_mtech",
        "title": "PG Admissions (M.Tech, MBA, MCA)",
        "category": "admissions",
        "keywords": [
            "pg admission", "mtech admission", "mba admission", "mca admission", "pgcet",
            "gate", "kmat", "post graduate admission", "m tech admission"
        ],
        "answer": (
            "Postgraduate admissions for M.Tech, MBA, and MCA are routed through Karnataka PGCET, "
            "GATE for M.Tech, or KMAT for MBA and MCA programs. Details are available from the PG admissions desk."
        )
    },
    {
        "id": "fees_and_scholarships",
        "title": "Fees and Scholarships",
        "category": "admissions",
        "keywords": [
            "fees", "fee structure", "how much fee", "college fees", "scholarship",
            "scholarships", "ssp scholarship", "nsp scholarship", "vidyasiri", "fee concession",
            "pay fees", "tuition fee"
        ],
        "answer": (
            "Tuition fees are determined as per government and CET/COMEDK regulations. Eligible students "
            "can apply for state and central government scholarships such as SSP, NSP, Vidyasiri, and "
            "merit-cum-means awards. Fee payments can be made online via the official portal at sit.ac.in."
        )
    },
    {
        "id": "placements_overview",
        "title": "Placements and Training Overview",
        "category": "placements",
        "keywords": [
            "placement", "placements", "campus placement", "training and placement",
            "placement cell", "jobs", "job offers", "placement record", "how is placement",
            "placement of our college", "tell me the placement of our college",
            "tell me about placement of our college", "placements at our college", "placements in sit",
            "placement department", "campus recruitment"
        ],
        "answer": (
            "SIT has a proactive Department of Training and Placements that bridges academia and industry. "
            "Over 100 reputed companies visit SIT annually, and students undergo pre-placement training "
            "covering quantitative aptitude, soft skills, and mock interviews from their second year onwards."
        )
    },
    {
        "id": "placements_statistics",
        "title": "Placement Packages and Statistics",
        "category": "placements",
        "keywords": [
            "highest package", "average package", "package", "salary", "packages",
            "highest salary", "average salary", "lpa", "placement statistics", "max package",
            "placement package", "how much package", "highest package in cse", "highest package in placement"
        ],
        "answer": (
            "Placement figures vary by graduating batch. The SIT placement page publishes year-wise highest "
            "and average packages, offers, and companies; consult the latest published batch figures."
        )
    },
    {
        "id": "top_recruiters",
        "title": "Top Recruiting Companies",
        "category": "placements",
        "keywords": [
            "recruiters", "recruiting companies", "top companies", "which companies visit",
            "amazon", "cisco", "tcs", "infosys", "wipro", "mercedes", "jp morgan",
            "target", "hiring companies"
        ],
        "answer": (
            "Top recruiters visiting SIT include Amazon, Cisco, Target, Twilio, Mercedes-Benz, "
            "JP Morgan Chase, TCS, Infosys, Wipro, Accenture, Bosch, Mindtree, L&T, and Dell, "
            "among dozens of other multinational and core engineering leaders."
        )
    },
    {
        "id": "hostel_boys",
        "title": "Boys Hostel Facilities",
        "category": "hostel",
        "keywords": [
            "boys hostel", "boy hostel", "gents hostel", "boys stay", "boys accommodation",
            "boys rooms", "diamond jubilee hostel", "hostel for boys", "how many boys hostel"
        ],
        "answer": (
            "SIT provides separate boys' and girls' hostels with furnished rooms, vegetarian mess, Wi-Fi, "
            "study and recreation spaces, and wardens. Check the official hostel page for current availability."
        )
    },
    {
        "id": "hostel_girls",
        "title": "Girls Hostel Facilities",
        "category": "hostel",
        "keywords": [
            "girls hostel", "girl hostel", "ladies hostel", "girls stay", "girls accommodation",
            "hostel for girls", "girls security", "women hostel"
        ],
        "answer": (
            "SIT provides separate girls' hostel accommodation with furnished rooms, mess, Wi-Fi, study and "
            "recreation spaces, and wardens. Check the official hostel page for current availability and rules."
        )
    },
    {
        "id": "hostel_mess_food",
        "title": "Hostel Mess and Dining",
        "category": "hostel",
        "keywords": [
            "hostel food", "mess", "hostel mess", "food in hostel", "vegetarian food",
            "is non veg allowed", "hostel meals", "hostel dining", "boy hostel mess", "girls hostel mess"
        ],
        "answer": (
            "The SIT hostel mess serves strictly nutritious, hygienic vegetarian food with balanced South "
            "and North Indian menus. Modern mechanized kitchens ensure cleanliness, and RO purified drinking "
            "water is supplied round the clock."
        )
    },
    {
        "id": "hostel_timings_rules",
        "title": "Hostel Timings and Discipline",
        "category": "hostel",
        "keywords": [
            "hostel timing", "hostel timings", "in time", "curfew", "gate time for hostel",
            "hostel rules", "night out", "permission for hostel", "gate pass"
        ],
        "answer": (
            "Hostel residents must adhere to evening in-times: typically 7:30 PM for the girls hostel "
            "and 8:30 PM for the boys hostel. Leaving campus overnight requires an approved gate pass "
            "from the hostel warden and parental intimation."
        )
    },
    {
        "id": "central_library",
        "title": "Central Library",
        "category": "facilities",
        "keywords": [
            "library", "central library", "books in library", "reading room", "library timings",
            "digital library", "ieee xplore", "how many books", "delnet", "journals", "library open"
        ],
        "answer": (
            "SIT's Central Library houses over 130,000 volumes, hundreds of national and international "
            "print journals, and e-resources like IEEE Xplore, ScienceDirect, and Springer. It includes "
            "a large reading room and a digital library wing, usually open from 8:00 AM to 10:00 PM."
        )
    },
    {
        "id": "birla_auditorium",
        "title": "Birla Auditorium",
        "category": "facilities",
        "keywords": [
            "birla auditorium", "auditorium", "birla audi", "audi in sit", "air conditioned auditorium",
            "where is auditorium", "convocation hall", "seminar hall"
        ],
        "answer": (
            "The Birla Auditorium is SIT's premier air-conditioned auditorium with state-of-the-art "
            "audio-visual systems and a seating capacity of over 1,000. It hosts major conferences, "
            "annual convocations, and technical symposiums."
        )
    },
    {
        "id": "gandhi_bhavan",
        "title": "Gandhi Bhavan",
        "category": "facilities",
        "keywords": [
            "gandhi bhavan", "gandhi hall", "where is gandhi bhavan", "multipurpose hall"
        ],
        "answer": (
            "Gandhi Bhavan is a distinguished multi-purpose hall on campus used for student cultural "
            "gatherings, guest lectures, club events, and institute-level ceremonies."
        )
    },
    {
        "id": "canteen_and_cafeteria",
        "title": "Canteen and Food Courts",
        "category": "facilities",
        "keywords": [
            "canteen", "cafeteria", "food court", "hotel in sit", "snacks in college",
            "coffee", "tea", "where can i eat", "canteen food", "nescafe kiosk"
        ],
        "answer": (
            "The college features a large main canteen serving South Indian meals, dosas, snacks, "
            "and beverages at subsidized student prices, alongside popular coffee kiosks and food stalls "
            "situated near academic departments."
        )
    },
    {
        "id": "health_centre",
        "title": "Health Centre and Medical Emergency",
        "category": "facilities",
        "keywords": [
            "health centre", "hospital", "clinic", "medical facility", "doctor on campus",
            "dispensary", "first aid", "ambulance", "emergency medical", "sick in college"
        ],
        "answer": (
            "SIT has an on-campus Health Centre with a resident medical officer and nursing staff "
            "providing free medical checkups, primary consultation, and first aid. A 24/7 dedicated "
            "ambulance is on standby with tie-ups to nearby super-specialty hospitals."
        )
    },
    {
        "id": "bank_atm_post",
        "title": "Bank, ATM and Post Office",
        "category": "facilities",
        "keywords": [
            "bank", "canara bank", "atm", "cash machine", "post office",
            "is there an atm", "banking on campus", "postal service on campus"
        ],
        "answer": (
            "A full-fledged Canara Bank branch with an on-site 24/7 ATM operates right on the SIT campus, "
            "along with a government Post Office and a student co-operative stationery store."
        )
    },
    {
        "id": "sports_and_gym",
        "title": "Sports, Stadium and Gymnasium",
        "category": "facilities",
        "keywords": [
            "sports", "ground", "playground", "gym", "gymnasium", "cricket ground",
            "football ground", "badminton court", "tennis court", "basketball court", "fitness centre"
        ],
        "answer": (
            "The Department of Physical Education provides excellent sports infrastructure: a full-sized "
            "cricket ground, football field, 400-meter athletic track, synthetic basketball and tennis courts, "
            "indoor wooden badminton courts, table tennis, and a modern multi-station fitness gymnasium."
        )
    },
    {
        "id": "cse_department",
        "title": "Computer Science and Engineering (CSE)",
        "category": "academics",
        "keywords": [
            "cse", "computer science", "cs branch", "cse department", "cse hod",
            "labs in cse", "computer science and engineering"
        ],
        "answer": (
            "The Department of Computer Science & Engineering is one of SIT's flagship departments, "
            "equipped with high-performance computing labs, advanced AI, cloud, and cybersecurity research "
            "centers. It enjoys top placement records with recruiters like Amazon, Cisco, and Microsoft."
        )
    },
    {
        "id": "ise_department",
        "title": "Information Science and Engineering (ISE)",
        "category": "academics",
        "keywords": [
            "ise", "information science", "is branch", "ise department", "info sci branch",
            "information science and engineering"
        ],
        "answer": (
            "The Department of Information Science & Engineering focuses on data engineering, full-stack "
            "web technologies, mobile computing, and information security. It shares outstanding placement "
            "opportunities alongside the CSE department."
        )
    },
    {
        "id": "aiml_department",
        "title": "Artificial Intelligence & Machine Learning (AI & ML)",
        "category": "academics",
        "keywords": [
            "aiml", "ai ml", "ai and ml", "artificial intelligence branch", "machine learning branch",
            "aiml branch", "aiml department", "ai branch"
        ],
        "answer": (
            "The AI & ML department trains students in deep learning, natural language processing, "
            "computer vision, and robotics using GPU-accelerated computing infrastructure and industry-partnered labs."
        )
    },
    {
        "id": "aids_department",
        "title": "Artificial Intelligence & Data Science (AI & DS)",
        "category": "academics",
        "keywords": [
            "aids", "ai ds", "ai and ds", "data science branch",
            "aids department", "big data branch"
        ],
        "answer": (
            "The AI & Data Science department specializes in big data analytics, statistical modeling, "
            "data visualization, and predictive intelligence to prepare graduates for high-demand data roles."
        )
    },
    {
        "id": "ece_department",
        "title": "Electronics and Communication Engineering (ECE)",
        "category": "academics",
        "keywords": [
            "ece", "electronics", "ec branch", "ece department", "vlsi lab", "embedded systems",
            "electronics and communication"
        ],
        "answer": (
            "The ECE Department is known for its excellence in VLSI design, embedded systems, IoT, and "
            "wireless communications, equipped with state-of-the-art Cadence, Synopsys, and DSP laboratories."
        )
    },
    {
        "id": "eee_department",
        "title": "Electrical and Electronics Engineering (EEE)",
        "category": "academics",
        "keywords": [
            "eee", "electrical", "triple e", "eee department", "electrical engineering",
            "power systems", "electric vehicle"
        ],
        "answer": (
            "The Department of Electrical & Electronics Engineering focuses on power systems, renewable energy, "
            "electric vehicle (EV) drive trains, control engineering, and industrial automation."
        )
    },
    {
        "id": "ete_department",
        "title": "Electronics and Telecommunication Engineering (ETE)",
        "category": "academics",
        "keywords": [
            "ete", "telecom", "telecommunication", "ete department", "5g lab",
            "microwave lab", "optical communication"
        ],
        "answer": (
            "The ETE Department specializes in microwave communication, optical networks, 5G wireless systems, "
            "and RF engineering, supported by a specialized 5G use-case laboratory."
        )
    },
    {
        "id": "mech_department",
        "title": "Mechanical Engineering",
        "category": "academics",
        "keywords": [
            "mech", "mechanical", "mechanical engineering", "mech department", "cad cam lab",
            "robotics in mech", "workshop in sit", "thermodynamics"
        ],
        "answer": (
            "Established in 1963, the Mechanical Engineering Department features CNC machines, 3D printing labs, "
            "robotics cells, and automotive test-rigs, with student teams participating in national SAE competitions."
        )
    },
    {
        "id": "civil_department",
        "title": "Civil Engineering",
        "category": "academics",
        "keywords": [
            "civil", "civil engineering", "civil department", "structural engineering",
            "surveying in sit", "concrete lab", "geotechnical"
        ],
        "answer": (
            "The Civil Engineering Department is one of the founding departments of SIT, renowned for structural "
            "testing, GIS surveying, environmental engineering, and extensive consultancy services across Karnataka."
        )
    },
    {
        "id": "chem_department",
        "title": "Chemical Engineering",
        "category": "academics",
        "keywords": [
            "chemical", "chemical engineering", "chem branch", "chemical department",
            "process engineering", "reaction engineering"
        ],
        "answer": (
            "The Chemical Engineering Department trains students in reaction engineering, separation processes, "
            "and green chemical technology, with research labs sponsored by AICTE and DST."
        )
    },
    {
        "id": "biotech_department",
        "title": "Biotechnology Department",
        "category": "academics",
        "keywords": [
            "biotech", "biotechnology", "bt branch", "biotechnology department",
            "genetic engineering in sit", "fermentation lab"
        ],
        "answer": (
            "The Biotechnology Department offers research-driven learning in bioinformatics, bioprocess engineering, "
            "plant tissue culture, and molecular biology with dedicated fermentation and cell culture labs."
        )
    },
    {
        "id": "iem_department",
        "title": "Industrial Engineering and Management (IEM)",
        "category": "academics",
        "keywords": [
            "iem", "industrial engineering", "industrial engineering and management",
            "supply chain management", "operations research"
        ],
        "answer": (
            "The IEM Department merges engineering principles with business administration, focusing on "
            "supply chain management, ergonomics, total quality management, and manufacturing systems."
        )
    },
    {
        "id": "architecture_department",
        "title": "Department of Architecture (B.Arch)",
        "category": "academics",
        "keywords": [
            "architecture", "barch", "b arch", "architecture department", "design studio in sit",
            "council of architecture", "5 year architecture course"
        ],
        "answer": (
            "The Department of Architecture offers a recognized 5-year B.Arch program approved by the Council "
            "of Architecture (CoA), equipped with modern design studios, model-making workshops, and climatology labs."
        )
    },
    {
        "id": "mba_mca_departments",
        "title": "MBA and MCA Programs",
        "category": "academics",
        "keywords": [
            "mba", "mca", "master of business administration", "master of computer applications",
            "mba department", "mca department", "management studies"
        ],
        "answer": (
            "SIT offers dedicated postgraduate programs: the MBA department offers dual specializations in "
            "Finance, Marketing, HR, and Business Analytics, while the MCA department prepares software developers "
            "with a focus on cloud computing and application development."
        )
    },
    {
        "id": "autonomous_academic_system",
        "title": "Autonomous Credit System",
        "category": "regulations",
        "keywords": [
            "autonomous", "credit system", "cbcs", "how many credits", "curriculum of sit",
            "vtu autonomous", "academic regulations", "syllabus of sit"
        ],
        "answer": (
            "SIT is an autonomous institute affiliated with VTU. Programme curricula, regulations, and "
            "electives are published through the official Academics and Academic Procedure pages."
        )
    },
    {
        "id": "cie_and_see_exams",
        "title": "Internal (CIE) and Semester (SEE) Exams",
        "category": "regulations",
        "keywords": [
            "cie", "see", "exams", "internals", "internal test", "semester exam", "end exam",
            "coe", "controller of examinations", "exam marks", "cie marks"
        ],
        "answer": (
            "SIT publishes programme and batch specific rules for Continuous Internal Evaluation (CIE) and "
            "Semester End Examinations (SEE). Check the current rules and Controller of Examinations page "
            "for mark distribution, eligibility, and exam notices."
        )
    },
    {
        "id": "attendance_rules",
        "title": "Attendance Requirement (85% Rule)",
        "category": "regulations",
        "keywords": [
            "attendance", "attendance rule", "minimum attendance", "attendance percentage",
            "condonation", "shortage of attendance", "75 percent attendance", "85 percent attendance"
        ],
        "answer": (
            "SIT's current attendance guidelines require at least 85% attendance in each subject for semester "
            "exam eligibility. Attendance and IA rules may vary by programme and batch; check the current "
            "official guideline and regulations."
        )
    },
    {
        "id": "grading_system_cgpa",
        "title": "Grading System, SGPA, and CGPA",
        "category": "regulations",
        "keywords": [
            "grading", "sgpa", "cgpa", "grade points", "distinction", "first class",
            "how is cgpa calculated", "10 point scale", "grading system"
        ],
        "answer": (
            "Academic performance is assessed on a 10-point scale: Grades range from 'O' (Outstanding - 10 points) "
            "down to 'P' (Pass - 4 points), with 'F' indicating fail. Semester Grade Point Average (SGPA) and "
            "Cumulative Grade Point Average (CGPA) reflect continuous student achievement."
        )
    },
    {
        "id": "halcyon_fest",
        "title": "Halcyon - Annual Cultural Fest",
        "category": "events",
        "keywords": [
            "halcyon", "fest", "cultural fest", "annual fest", "college fest",
            "halcyon fest", "when is halcyon", "celebrity night", "pro night", "dance competition"
        ],
        "answer": (
            "'Halcyon' is SIT's flagship annual national-level inter-collegiate cultural festival. "
            "Held every spring, it attracts thousands of students across India for music battles, "
            "dance competitions, fine arts, and high-energy celebrity pro-nights."
        )
    },
    {
        "id": "sit_expo_tech_fest",
        "title": "SIT Expo and Technical Fests",
        "category": "events",
        "keywords": [
            "sit expo", "expo", "tech fest", "project exhibition", "final year project",
            "innovation exhibition", "science fest", "technical events"
        ],
        "answer": (
            "'SIT Expo' is the prestigious annual project exhibition where final-year engineering students "
            "showcase innovative hardware prototypes, software solutions, and patents before panels of "
            "distinguished industry judges and startup investors."
        )
    },
    {
        "id": "clubs_and_societies",
        "title": "Student Clubs and Technical Societies",
        "category": "activities",
        "keywords": [
            "clubs", "student clubs", "ieee", "csi", "robocore", "robotics club",
            "rotaract", "spic macay", "coding club", "sae baja", "technical clubs in sit"
        ],
        "answer": (
            "SIT fosters vibrant student life with dozens of active clubs: IEEE Student Branch, CSI Chapter, "
            "Robocore (Robotics Club), SAE Collegiate Club (Baja/Supra racing cars), Rotaract Club, Spic Macay, "
            "Photography Club, and the SIT Literary Society."
        )
    },
    {
        "id": "ncc_and_nss",
        "title": "NCC and NSS Units",
        "category": "activities",
        "keywords": [
            "ncc", "nss", "cadet", "national cadet corps", "national service scheme",
            "social service", "blood donation", "air wing", "army wing"
        ],
        "answer": (
            "SIT has active NCC Army and Air Wings enabling students to earn 'B' and 'C' certificates, "
            "as well as an enthusiastic NSS unit that organizes regular blood donation drives, village adoptions, "
            "and environmental sustainability campaigns."
        )
    },
    {
        "id": "incubation_tbi_idea_lab",
        "title": "Startup Incubation (TBI) and AICTE IDEA Lab",
        "category": "facilities",
        "keywords": [
            "tbi", "incubation", "startups in sit", "idea lab", "aicte idea lab", "entrepreneurship",
            "patent", "research lab in sit", "maker space", "innovation in sit"
        ],
        "answer": (
            "SIT hosts a dedicated Technology Business Incubator (TBI) and an AICTE 5D IDEA Lab "
            "equipped with laser cutters, 3D printers, and IoT testbeds to help students transform innovative "
            "ideas into registered patent-backed startups."
        )
    },
    {
        "id": "anti_ragging_policy",
        "title": "Anti-Ragging and Student Safety",
        "category": "regulations",
        "keywords": [
            "anti ragging", "ragging", "is ragging allowed", "ragging complaint",
            "student safety", "grievance", "zero tolerance ragging"
        ],
        "answer": (
            "SIT maintains a strict Zero Tolerance policy against ragging. An active Anti-Ragging Committee "
            "and mobile squad monitor the campus and hostels round the clock. Any student found engaging in "
            "ragging faces immediate suspension and criminal prosecution under the law."
        )
    },
    {
        "id": "college_timings_dress_code",
        "title": "College Timings and Dress Code",
        "category": "regulations",
        "keywords": [
            "college timings", "timings of sit", "college time", "what time does college start",
            "closing time of sit", "dress code in sit", "uniform in sit", "id card rule"
        ],
        "answer": (
            "Academic classes typically run from 8:00 AM or 9:00 AM to 5:00 PM, Monday through Friday, "
            "with alternate Saturdays working as per the academic calendar. Students must wear their official "
            "college ID card visibly on campus at all times and adhere to decent, professional attire."
        )
    },
    {
        "id": "wifi_and_internet",
        "title": "Campus Wi-Fi and Internet",
        "category": "facilities",
        "keywords": [
            "wifi", "wi fi", "internet in campus", "campus wifi", "hostel wifi",
            "is wifi available", "broadband in sit"
        ],
        "answer": (
            "The entire SIT campus and all hostels are covered by a high-speed secure gigabit optical fiber "
            "network and Wi-Fi access points, enabling seamless access to academic journals and learning portals."
        )
    },
    {
        "id": "green_initiatives",
        "title": "Green Initiatives and Sustainability",
        "category": "overview",
        "keywords": [
            "green campus", "solar power in sit", "rainwater harvesting in sit", "clean campus",
            "environmental sustainability", "eco friendly sit"
        ],
        "answer": (
            "SIT is a clean, eco-friendly campus featuring rooftop solar power generation, comprehensive "
            "rainwater harvesting systems, a sewage treatment plant (STP) for landscape irrigation, and "
            "a plastic-conscious green environment."
        )
    },
    {
        "id": "greetings",
        "title": "Greetings and Welcome",
        "category": "conversation",
        "keywords": [
            "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
            "namaskara", "namaste", "vanakkam", "what's up", "how are you"
        ],
        "answer": (
            "Namaskara! Welcome to Siddaganga Institute of Technology, Tumakuru. "
            "I am your campus humanoid robot. How can I help you today?"
        )
    },
    {
        "id": "audio_check",
        "title": "Microphone Check",
        "category": "conversation",
        "keywords": [
            "can you hear me", "do you hear me", "are you listening", "can you hear my voice",
            "is my microphone working", "mic check", "testing microphone", "hello robo can you hear me"
        ],
        "answer": "Yes, I can hear you. Please ask me about Siddaganga Institute of Technology, or say Robo stop to exit."
    },
    {
        "id": "thanks_and_bye",
        "title": "Thanks and Farewell",
        "category": "conversation",
        "keywords": [
            "thank you", "thanks", "thank u", "bye", "goodbye", "see you", "exit",
            "quit", "stop", "dhanyavada", "thanks a lot"
        ],
        "answer": (
            "You are most welcome! Wishing you great success at Siddaganga Institute of Technology. "
            "Have a wonderful day!"
        )
    },
    {
        "id": "help_capabilities",
        "title": "What Can You Ask",
        "category": "conversation",
        "keywords": [
            "help", "what can you do", "what can i ask", "topics", "options", "menu",
            "guide", "commands", "how to use"
        ],
        "answer": (
            "You can ask me anything about SIT: Principal & Leadership, Engineering Departments, "
            "Placements & Packages, Admissions & KCET cutoffs, Hostel facilities & food, Central Library, "
            "Birla Auditorium, Campus Sports, Halcyon fest, or College rules and timings."
        )
    }
]


# These reviewed updates correct older entries and add SIT information from
# the official public pages. Keeping them here ensures rebuilding the JSON
# database does not discard the expanded campus knowledge.
TOPIC_UPDATES = {
    "about_sit": {
        "answer": "Siddaganga Institute of Technology (SIT) in Tumakuru was established in 1963. It is an autonomous institute affiliated with Visvesvaraya Technological University, approved by AICTE, and accredited with NAAC A++.",
        "sources": ["https://sit.ac.in/about/"],
    },
    "location_address": {
        "answer": "SIT is at Dr. Sree Sree Sivakumara Swamiji Road, Tumakuru, Karnataka 572103. The official website has campus directions and current contact details.",
        "sources": ["https://sit.ac.in/contact-us/"],
    },
    "contact_details": {
        "answer": "SIT's official contact page lists principal@sit.ac.in and admissions phone numbers 0816-2282696, 0816-2214001, and 0816-2214002. Check the website for the right office and current details.",
        "sources": ["https://sit.ac.in/contact-us/"],
    },
    "how_to_reach": {
        "answer": "SIT is on Dr. Sree Sree Sivakumara Swamiji Road in Tumakuru, Karnataka 572103. Use the map linked from the official Contact Us page for directions from your starting point.",
        "sources": ["https://sit.ac.in/contact-us/"],
    },
    "admissions_kcet_comedk": {
        "answer": "SIT undergraduate admissions include routes through Karnataka CET (KEA), COMEDK, and other applicable admission categories. Eligibility, seat availability, admission steps, and current year cutoffs can change; use the official SIT Admission page and the relevant entrance authority's current notice. I do not have a verified current cutoff rank.",
        "sources": ["https://sit.ac.in/", "https://sit.ac.in/admission/", "https://sit.ac.in/doc-required/"],
    },
    "admissions_management_quota": {
        "answer": "Admission categories and seat availability depend on the programme and current admission cycle. Check the official SIT Admission page for the current process and contact the admissions office for management-category enquiries; do not rely on last year's fees or seat details.",
        "sources": ["https://sit.ac.in/admission/"],
    },
    "fees_and_scholarships": {
        "answer": "SIT lists scholarships from Karnataka and central government schemes, private organizations, and institute merit or endowment awards. Eligibility and application dates vary by scheme. Check the official Scholarship page and confirm current fee details with admissions; I do not have a verified current fee amount.",
        "sources": ["https://sit.ac.in/scholarship/", "https://sit.ac.in/admission/"],
    },
    "placements_overview": {
        "answer": "SIT's Department of Training and Placements provides placement support, training, mentoring, and employer connections. The official placement page publishes year-wise metrics; figures change by graduating batch.",
        "sources": ["https://sit.ac.in/sit-placements/"],
    },
    "placements_statistics": {
        "answer": "SIT's placement page lists 2024–25 results as a highest package of 32.88 LPA, an average package of 9.00 LPA, 1,066 offers, and 240 companies. The 2025–26 batch figures are marked in progress on the site, so check the current placement page for updates.",
        "sources": ["https://sit.ac.in/sit-placements/"],
    },
    "top_recruiters": {
        "answer": "SIT's placement page features recruiters and year-wise placement updates. Recruiters vary by batch; use the current Training and Placements page for the latest company list.",
        "sources": ["https://sit.ac.in/sit-placements/"],
    },
    "hostel_boys": {
        "answer": "SIT provides separate boys' and girls' hostels with furnished rooms, vegetarian mess, Wi-Fi, study and recreation spaces, and wardens. Check the official Hostel page or contact the hostel office for current block details, availability, and fees.",
        "sources": ["https://sit.ac.in/hostel/"],
    },
    "hostel_girls": {
        "answer": "SIT provides separate girls' hostel accommodation with furnished rooms, mess, Wi-Fi, study and recreation spaces, and wardens. Check the official hostel page for current availability and rules.",
        "sources": ["https://sit.ac.in/hostel/"],
    },
    "central_library": {
        "answer": "SIT's Central Library has print and digital collections, book-bank services, reading halls, an online catalogue, and access to e-resources. The library website lists current hours and services; during examinations it reports 24-hour access.",
        "sources": ["https://sit.ac.in/library/"],
    },
    "health_centre": {
        "answer": "SIT's Health Centre provides outpatient and day-care services, referrals, vaccination, basic tests, and ambulance support for students and staff. The official page lists weekday hours as 9 a.m.–1 p.m. and 3–6 p.m., Saturday 9 a.m.–1 p.m., and phone 0816-2214075. Call ahead for current availability.",
        "sources": ["https://sit.ac.in/health-centre/"],
    },
    "clubs_and_societies": {
        "answer": "SIT has technical, cultural, and professional student groups. Examples include Robotics, Decoders, Pathfinders, TEDx, NASA, SARC, QUEST, Team Codon, TAR Racing, Soaring Eagles, Adrenaline Racing, Script Ink, AI Brewery, Halcyon, Quizzing Inc, The Book Cult, IEEE groups, CSI, ISTE, ICI, and ASCE. The official Clubs page has the broader current directory; club activity and membership can change each year.",
        "sources": ["https://sit.ac.in/clubs/", "https://sit.ac.in/campus/"],
    },
    "attendance_rules": {
        "answer": "SIT's Attendance and Internal Assessment Guidelines page says attendance is calculated separately for each subject and sets a minimum of 85% attendance in each subject for semester exam eligibility. The page also states a minimum of 35% IA marks per subject. Check the current rules for your programme and batch, because regulations and assessment details can change.",
        "sources": ["https://sit.ac.in/attendance/", "https://sit.ac.in/academic-procedure/"],
    },
    "cie_and_see_exams": {
        "answer": "SIT publishes programme and batch specific rules for Continuous Internal Evaluation (CIE) and Semester End Examinations (SEE). Check the current Academic Rules and Regulations and the Controller of Examinations page for mark distribution, eligibility, and exam notices.",
        "sources": ["https://sit.ac.in/academic-procedure/", "https://sit.ac.in/controller-of-examinations/"],
    },
}

EXTRA_TOPICS = [
    {
        "id": "academic_calendar",
        "title": "Academic Calendar and Semester Dates",
        "category": "academics",
        "keywords": ["academic calendar", "semester calendar", "college calendar", "semester dates", "first semester dates", "exam dates", "holiday list", "class commencement", "academic year calendar", "2025 26 calendar"],
        "answer": "SIT publishes separate academic calendars by programme and semester. The Academic Procedure page lists the 2025–26 calendars for B.E., B.Arch., M.Tech., MBA, and MCA. Check the calendar for your course and semester because dates differ by programme and can be revised.",
        "sources": ["https://sit.ac.in/academic-procedure/"],
    },
    {
        "id": "academic_rules_source",
        "title": "Where to Find Academic Rules",
        "category": "regulations",
        "keywords": ["rules and regulations", "academic rules", "college rules", "student rules", "regulation pdf", "attendance rules pdf", "exam rules", "discipline rules", "academic procedure"],
        "answer": "SIT's Academic Procedure page links the current UG and PG rules, Ph.D. rules, academic calendars, and 2025–26 academic rules document. Rules depend on programme and batch, so use the applicable document or ask your department for clarification.",
        "sources": ["https://sit.ac.in/academic-procedure/"],
    },
    {
        "id": "departments_and_programs",
        "title": "Departments and Programs at SIT",
        "category": "academics",
        "keywords": ["departments", "all branches", "all courses", "what branches are available", "engineering branches", "courses offered", "programs offered", "ug courses", "pg courses", "list of departments"],
        "answer": "SIT's directory lists Architecture, Artificial Intelligence and Data Science, Biotechnology, Chemical Engineering, Civil Engineering, Computer Science and Engineering, CSE Artificial Intelligence and Machine Learning, Electronics and Communication, Electrical and Electronics, Electronics and Instrumentation, Electronics and Telecommunication, Industrial Engineering and Management, Information Science, Mechanical Engineering, MBA, MCA, Chemistry, Mathematics, Physics, and the Internal Quality Assurance Cell. The directory shows current programs and department pages.",
        "sources": ["https://sit.ac.in/department/", "https://sit.ac.in/about/"],
    },
    {
        "id": "research_centres",
        "title": "Research and Centres of Excellence",
        "category": "research",
        "keywords": ["research at sit", "research centers", "centres of excellence", "coe", "innovation labs", "research facilities", "phd research", "patents", "funded projects"],
        "answer": "SIT supports research through department research programs and specialized Centres of Excellence. The research page describes current facilities, projects, publications, Ph.D. activity, and industry partnerships; these figures are updated over time.",
        "sources": ["https://sit.ac.in/research-and-industry/", "https://sit.ac.in/coes/"],
    },
    {
        "id": "campus_facilities",
        "title": "Campus Facilities and Student Services",
        "category": "facilities",
        "keywords": ["campus facilities", "student services", "facilities in sit", "campus services", "post office", "cooperative society", "printing shop", "refreshment", "banking", "campus life"],
        "answer": "SIT's campus page lists facilities such as a health centre, co-operative society, post office, refreshment zone, printing and photocopy services, sports, yoga, gymnasium, hostels, NCC, NSS, and student clubs. Check the linked service page for details and current timings.",
        "sources": ["https://sit.ac.in/campus/", "https://sit.ac.in/students/"],
    },
    {
        "id": "admission_documents",
        "title": "Documents Needed for Admission",
        "category": "admissions",
        "keywords": ["admission documents", "documents required", "what documents for admission", "kcet admission documents", "comedk admission documents", "admission certificate", "documents for be admission", "joining documents"],
        "answer": "Required documents vary by programme and admission route. SIT's Documents Required page has separate lists for B.E. KCET, COMEDK, B.Arch., lateral entry, MBA, MCA, M.Tech., and research admissions. Check the list for your route and confirm originals and copies with the admissions office.",
        "sources": ["https://sit.ac.in/doc-required/", "https://sit.ac.in/admission/"],
    },
    {
        "id": "placement_yearwise_data",
        "title": "Recent Year-wise Placement Results",
        "category": "placements",
        "keywords": ["2024 placement statistics", "2025 placement statistics", "2023 placement statistics", "placement offers by year", "placement companies by year", "2024 25 placement", "placement average 2024 25", "highest package 2024 25"],
        "answer": "SIT's placement page reports: 2024–25, highest 32.88 LPA, average 9.00 LPA, 1,066 offers and 240 companies; 2023–24, highest 34.00 LPA, average 9.00 LPA, 950 offers and 230 companies; 2022–23, highest 41.54 LPA, average 8.50 LPA, 1,350 offers and 300 companies. Figures are as published by SIT and may be revised.",
        "sources": ["https://sit.ac.in/sit-placements/"],
    },
    {
        "id": "sip_club_introduction_2025",
        "title": "Student Induction Programme Club Introductions 2025",
        "category": "activities",
        "keywords": ["sip 2025", "student induction programme", "club introduction schedule", "which clubs presented at sip", "induction clubs", "club presentation", "student clubs 2025", "introduction to sit clubs"],
        "answer": "The 2025 Student Induction Programme club introduction schedule included AI Brewery, CORSIT, Decoders, GeeksforGeeks, IEEE Photonics and ComSoc, IEEE SIT Student Branch, IIC, ResearchGate, SARK, Soaring Eagles, Team Adrenaline Racing, Team Auto Architects, Team Sigma, Adlib Arts, Avalanche, Team Pathfinder, Team Quest, Quizzing Inc, TEDx, The Book Cult, and Team Scriptink. This is the 2025 induction list; check the current Clubs page for today's groups and activities.",
        "sources": ["https://sit.ac.in/clubs/", "https://sit.ac.in/campus/", "SIP CLUB INTRODUCTION TT.pdf (2025 schedule)"],
    },
    {
        "id": "health_centre_hours",
        "title": "Health Centre Timings and Emergency Support",
        "category": "facilities",
        "keywords": ["health centre timings", "medical centre timings", "doctor in college", "ambulance number", "college clinic number", "medical emergency", "health centre phone", "medical help on campus"],
        "answer": "The SIT Health Centre lists weekday service from 9 a.m. to 1 p.m. and 3 p.m. to 6 p.m., and Saturday service from 9 a.m. to 1 p.m. Its listed phone is 0816-2214075. For an emergency, contact campus staff or local emergency services as appropriate; confirm the centre's current hours by phone.",
        "sources": ["https://sit.ac.in/health-centre/"],
    },
    {
        "id": "choose_a_department",
        "title": "Choosing a Department",
        "category": "academics",
        "keywords": ["which branch should i choose", "which department is best", "best branch in sit", "help me choose a course", "which course suits me", "confused about branch", "branch selection help"],
        "answer": "There is no single best branch for everyone. Think about the subjects you enjoy and the kind of work you want to try. Tell me whether you prefer coding, electronics, design, biology, or business, and I can suggest departments to explore.",
        "sources": ["https://sit.ac.in/department/"],
    },
    {
        "id": "compare_computing_branches",
        "title": "Comparing CSE, ISE, AI and Data Science",
        "category": "academics",
        "keywords": ["difference between cse and ise", "cse or ise", "difference between ai ml and data science", "aiml or aids", "compare computer branches", "which computer branch is better"],
        "answer": "These programmes all involve computing, but they emphasize different areas. CSE is broad computer science; ISE focuses on information systems; AI and Data Science focus on learning from data and intelligent systems. Compare the current SIT curricula and choose based on what interests you.",
        "sources": ["https://sit.ac.in/department/"],
    },
    {
        "id": "admission_eligibility",
        "title": "Admission Eligibility and Cutoffs",
        "category": "admissions",
        "keywords": ["am i eligible for sit", "eligibility criteria", "marks required for admission", "what rank do i need", "kcet cutoff", "comedk cutoff", "admission cutoff rank", "minimum marks for admission"],
        "answer": "Eligibility and cutoffs depend on the programme, admission route, category, and current year. Tell me which course and route you’re considering, and check the latest SIT and entrance-authority notices before making a decision.",
        "sources": ["https://sit.ac.in/admission/", "https://sit.ac.in/doc-required/"],
    },
    {
        "id": "online_admission_enquiry",
        "title": "How to Contact Admissions",
        "category": "admissions",
        "keywords": ["apply online", "online admission form", "admission enquiry form", "how to apply to sit", "contact admissions", "admission office number", "admission help"],
        "answer": "You can send an admission enquiry through SIT’s official website or call the admissions office on 0816-2282696, 0816-2214001, or 0816-2214002. Have your course and entrance-exam details ready so they can guide you faster.",
        "sources": ["https://sit.ac.in/admission-form/", "https://sit.ac.in/contact-us/"],
    },
]

# Spoken replies are written for a person standing in front of the robot.
# Keep the wording short and conversational; the source corpus holds detail for
# retrieval, while these answers provide the quick campus-guide response.
FRIENDLY_ANSWERS = {
    "identity": "I’m your SIT campus guide. Ask me about courses, admissions, placements, hostels, clubs, or campus services. What can I help you find?",
    "about_sit": "SIT is an autonomous engineering and technology institute in Tumakuru. It was founded in 1963 and is affiliated with VTU. Would you like to hear about courses or campus life?",
    "founder_swamiji": "SIT was founded by Dr. Sree Sree Shivakumara Swamigalu. He was known for supporting education, food, and shelter through Siddaganga Math.",
    "president_swamiji": "The Sree Siddaganga Education Society is guided by Sree Sree Siddalinga Swamigalu, continuing the educational work of the Math.",
    "principal_sit": "SIT’s Principal is Dr. S. V. Dinesh. If you’re looking for a particular office, tell me what you need and I’ll point you in the right direction.",
    "leadership_management": "For the latest director and management details, the college office can connect you with the right person. The official contact number is 0816-2214001.",
    "location_address": "We’re on Dr. Sree Sree Sivakumara Swamiji Road in Tumakuru, Karnataka, PIN 572103. I can help you find the map or contact details too.",
    "how_to_reach": "SIT is in Tumakuru on Dr. Sree Sree Sivakumara Swamiji Road. Open the Contact Us page on the SIT website for a map and directions from where you are.",
    "contact_details": "You can reach the admissions office on 0816-2282696, 0816-2214001, or 0816-2214002. The main email is principal@sit.ac.in.",
    "admissions_kcet_comedk": "For undergraduate admission, SIT lists KCET code E016 and COMEDK code E125. Cutoffs and seat availability change each year, so check the current admission notice. Are you applying through KCET or COMEDK?",
    "admissions_management_quota": "Management-category seats depend on the course and current admission cycle. Call the admissions office on 0816-2282696 and ask about the course you want; they can confirm the current process and fees.",
    "admissions_pg_mba_mca_mtech": "For M.Tech, MBA, or MCA, the entrance route depends on the course and admission category. Tell me which programme you’re interested in, and I can help you find the right admissions page.",
    "fees_and_scholarships": "SIT lists government, institute, donor, and merit scholarships. The amounts and eligibility vary, so the Accounts Office can help you find the ones that fit your situation. For current fees, please check with Admissions.",
    "placements_overview": "SIT’s Training and Placements team helps students prepare for jobs through training, mentoring, and employer connections. The figures change by graduating batch, so I can also share the latest published results.",
    "placements_statistics": "For the 2024–25 batch, SIT reports an average package of 9 lakh rupees per year and a highest package of 32.88 lakh. Those figures are for that batch; newer results may change.",
    "top_recruiters": "Companies visiting SIT can change from year to year. The placement office publishes the current recruiter list, and I can tell you about the latest batch results too.",
    "hostel_boys": "SIT has separate boys’ and girls’ hostels, with rooms, a vegetarian mess, Wi-Fi, study areas, and wardens. Ask the hostel office about current room availability and fees.",
    "hostel_girls": "SIT has separate girls’ hostel accommodation with a mess, Wi-Fi, study areas, recreation spaces, and wardens. The hostel office can confirm current availability and rules.",
    "hostel_mess_food": "The hostel mess serves vegetarian meals. If you’re staying in the hostel, the warden can tell you the current menu and meal timings.",
    "hostel_timings_rules": "Hostel entry and leave rules can depend on the hostel and current policy. Before planning a late return or overnight leave, please check with your warden.",
    "central_library": "The Central Library has books, reading spaces, book-bank services, and online learning resources. Its hours can change during exams, so check the library page for today’s timings.",
    "birla_auditorium": "Birla Auditorium is one of the main venues for college events, talks, and large gatherings. If you’re going to a particular programme, check its notice for the venue and time.",
    "gandhi_bhavan": "Gandhi Bhavan is a campus venue used for talks, gatherings, and student activities. Check the event notice to confirm where your programme is being held.",
    "canteen_and_cafeteria": "There are food and refreshment options on campus. The campus page has the current facilities; ask a student or staff member nearby for the closest one.",
    "health_centre": "If you’re feeling unwell, the campus Health Centre offers basic medical care and referrals. It lists weekday hours as 9 to 1 and 3 to 6, and Saturday hours as 9 to 1. You can call 0816-2214075 before going.",
    "bank_atm_post": "The campus has a co-operative society and a post office. For the nearest ATM or banking service, check the campus map or ask at the main office.",
    "sports_and_gym": "SIT has sports facilities, a gym, and recreation activities. The Sports page has current details; tell me which sport you’re looking for and I can help narrow it down.",
    "cse_department": "Computer Science and Engineering is a good place to explore software, computing, and problem-solving. Check the department page for its current courses and curriculum.",
    "ise_department": "Information Science and Engineering focuses on computing and information systems. If you’re comparing it with CSE, I can help explain the difference in simple terms.",
    "aiml_department": "Artificial Intelligence and Machine Learning focuses on how computers learn from data and solve problems such as language or image recognition. The department page has SIT’s current course details.",
    "aids_department": "Artificial Intelligence and Data Science brings together computing, statistics, and working with data. Check the department page for current subjects and programme details.",
    "ece_department": "Electronics and Communication Engineering covers electronics, communication systems, and connected devices. The department page has the current curriculum and facilities.",
    "eee_department": "Electrical and Electronics Engineering covers electrical systems, electronics, and areas such as energy and control. The department page has the current course details.",
    "ete_department": "Electronics and Telecommunication Engineering focuses on communication technologies and electronic systems. You can find the current subjects on its department page.",
    "mech_department": "Mechanical Engineering is about designing and making machines, products, and systems. The SIT department page can show you the current course structure and student activities.",
    "civil_department": "Civil Engineering focuses on the built environment, including structures, roads, water, and construction. The department page has SIT’s current course details.",
    "chem_department": "Chemical Engineering applies engineering to making and processing materials and products. Check the department page for current subjects, labs, and programme details.",
    "biotech_department": "Biotechnology combines biology with technology and engineering. The department page is the best place to see SIT’s current subjects and research areas.",
    "iem_department": "Industrial Engineering and Management looks at how to make systems, services, and workplaces work better. It combines engineering with planning and management.",
    "architecture_department": "SIT offers a five-year Bachelor of Architecture programme. It combines design, buildings, technology, and the way people use spaces.",
    "mba_mca_departments": "SIT offers MBA and MCA programmes. MBA focuses on business and management; MCA focuses on computing and applications. Tell me which one you’re considering and I’ll guide you to its course page.",
    "autonomous_academic_system": "SIT is autonomous, so it publishes its own programme curricula and academic rules while remaining affiliated with VTU. The Academic Procedure page has the current documents.",
    "cie_and_see_exams": "CIE means your internal assessment, and SEE is the semester-end exam. The exact marks and eligibility rules depend on your course and batch, so check your current regulations or ask your department.",
    "attendance_rules": "SIT’s current guideline says students need at least 85% attendance in each subject to be eligible for semester exams. It also lists an IA requirement. Check your batch’s rules or ask your department if you’re unsure.",
    "grading_system_cgpa": "SGPA is your grade-point average for one semester; CGPA combines your results across semesters. The exact grading rules are in the regulations for your programme and batch.",
    "halcyon_fest": "Halcyon is one of SIT’s student cultural festivals, with performances and activities. The dates and programme change each year, so look out for the current campus announcement.",
    "sit_expo_tech_fest": "SIT Expo gives students a chance to present projects and ideas. Check the current college notices for this year’s date, venue, and participation details.",
    "clubs_and_societies": "There are technical, cultural, and service groups at SIT. You’ll find options such as robotics, coding, racing, theatre, music, quizzing, and IEEE chapters. Are you more interested in technical or cultural clubs?",
    "ncc_and_nss": "NCC gives students a chance to take part in structured cadet training, while NSS focuses on community service. Ask the campus coordinators about joining and this year’s activities.",
    "incubation_tbi_idea_lab": "SIT has facilities to help students explore ideas and build prototypes, including an IDEA Lab and incubation support. If you have a project in mind, ask the relevant centre how students can get started.",
    "anti_ragging_policy": "If you’re worried about ragging or feel unsafe, tell a trusted faculty member or contact SIT’s Anti-Ragging Officer right away. The college lists the officer and contact details on its website.",
    "college_timings_dress_code": "Class times can differ by programme and semester. Please check your timetable or ask your department for today’s schedule; the Academic Calendar page lists important semester dates.",
    "wifi_and_internet": "SIT provides campus and hostel internet access for learning. If you’re having trouble connecting, ask your department or the campus IT support team for the current login steps.",
    "green_initiatives": "SIT highlights campus sustainability efforts, including solar power and rainwater harvesting. The Green Initiatives page has more about the projects currently in place.",
    "greetings": "Namaskara! Welcome to SIT. I’m your campus guide. What would you like help with today?",
    "audio_check": "Yes, I can hear you. Go ahead and ask me about SIT, or say “Robo stop” when you’re ready to finish.",
    "thanks_and_bye": "You’re welcome! I’m glad I could help. Have a good day at SIT.",
    "help_capabilities": "I can help with admissions, courses, departments, placements, hostels, the library, clubs, and campus services. Ask me a question the way you’d ask a campus guide.",
    "academic_calendar": "The calendar depends on your programme and semester. Open SIT’s Academic Procedure page and choose your course and semester to see the right dates.",
    "academic_rules_source": "Academic rules depend on your programme and batch. SIT’s Academic Procedure page links the calendars and rules; if you tell me your course, I can help you find the right section.",
    "departments_and_programs": "SIT has programmes in engineering, architecture, management, and computer applications. Tell me what subjects you enjoy, and I can help you find departments that may suit you.",
    "research_centres": "Students and faculty can explore research through SIT’s departments and specialist centres. The Research and Industry page gives an overview; ask me about a particular area if you have one in mind.",
    "campus_facilities": "On campus you’ll find student clubs, sports, a gym, a health centre, a post office, and other everyday services. What are you looking for? I can help you narrow it down.",
    "admission_documents": "The documents you need depend on your course and admission route. SIT has separate checklists for each one; tell me your programme and route, and I’ll point you to the right checklist.",
    "placement_yearwise_data": "Placement results change from batch to batch. SIT reports 1,066 offers from 240 companies for 2024–25; I can also share that year’s package figures if you’d like.",
    "sip_club_introduction_2025": "At the 2025 student induction, clubs introduced activities in coding, engineering, arts, quizzes, and more. Some names were AI Brewery, Decoders, Soaring Eagles, Team Quest, and The Book Cult. The current Clubs page has the latest list.",
    "health_centre_hours": "The Health Centre lists weekday hours as 9 to 1 and 3 to 6, and Saturday hours as 9 to 1. Call 0816-2214075 to check before you go.",
    "choose_a_department": "There isn’t one best branch for everyone. Tell me which subjects you like and what kind of work sounds interesting—coding, electronics, designing, biology, or business—and I’ll help you explore suitable departments.",
    "compare_computing_branches": "In simple terms, CSE gives you a broad computing foundation, ISE focuses more on information systems, and AI and Data Science focus on intelligent systems and data. The exact subjects differ, so compare SIT’s current course plans before choosing.",
    "admission_eligibility": "Eligibility and cutoffs depend on your course, admission route, category, and the current year. Which programme are you considering, and are you applying through KCET or COMEDK?",
    "online_admission_enquiry": "You can send an enquiry through SIT’s website or call Admissions on 0816-2282696, 0816-2214001, or 0816-2214002. If you tell me your course and entrance route, I can point you to the right page.",
}


def apply_reviewed_updates():
    topics_by_id = {topic["id"]: topic for topic in TOPICS}
    for topic_id, updates in TOPIC_UPDATES.items():
        if topic_id in topics_by_id:
            topics_by_id[topic_id].update(updates)
    for topic in EXTRA_TOPICS:
        if topic["id"] not in topics_by_id:
            TOPICS.append(topic)
            topics_by_id[topic["id"]] = topic
    for topic_id, answer in FRIENDLY_ANSWERS.items():
        if topic_id in topics_by_id:
            topics_by_id[topic_id]["answer"] = answer


apply_reviewed_updates()


def apply_dashboard_customizations():
    """Keep answers edited in Robo Brain when the reviewed base is rebuilt."""
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "knowledge_dashboard_state.json")
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    by_id = {topic["id"]: topic for topic in TOPICS}
    for override in state.get("overrides", []):
        topic_id = override.get("id")
        if not topic_id:
            continue
        if topic_id in by_id:
            by_id[topic_id].update(override)
        else:
            TOPICS.append(override)
            by_id[topic_id] = override
    deleted = set(state.get("deleted", []))
    if deleted:
        TOPICS[:] = [topic for topic in TOPICS if topic.get("id") not in deleted]


def main():
    apply_dashboard_customizations()
    print(f"Building knowledge.json with {len(TOPICS)} comprehensive topics...")
    total_keywords = sum(len(t["keywords"]) for t in TOPICS)
    print(f"Total keyword and alias variations indexed: {total_keywords}")

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(TOPICS, f, indent=2, ensure_ascii=False)

    print("Successfully generated knowledge.json!")


if __name__ == "__main__":
    main()
